"""The project as the rules see it: modules with their place in the layers, their imports, their classes with the
roles the building blocks give them. Read with `ast`; nothing of the project is imported or run."""

from __future__ import annotations

import ast
import builtins
import dataclasses
import functools
import os
import pathlib
import sys
from collections.abc import Iterator

from dca_rules.layout import DcaLayout

BB = "dca_building_blocks"

#: The building blocks' own hierarchy: a role implies its parents.
BB_PARENTS: dict[str, tuple[str, ...]] = {
    "Id": ("Value",),
    "EventId": ("Id",),
    "Timestamp": ("Value",),
    "AggregateRoot": ("Entity",),
    "UseCase": ("InputPort",),
    "AsyncUseCase": ("InputPort",),
    "Repository": ("OutputPort",),
    "Store": ("OutputPort",),
    "DomainEventPublisher": ("OutputPort",),
    "IntegrationEventPublisher": ("OutputPort",),
    "TransactionalEventListener": ("EventListener",),
    "InputPortException": ("PortException",),
    "UseCaseException": ("InputPortException",),
    "OutputPortException": ("PortException",),
}

STDLIB = frozenset(sys.stdlib_module_names) | {"__future__"}

#: Where a class's bases mean "a protocol".
PROTOCOL = {"typing.Protocol", "typing_extensions.Protocol"}
#: Where a class's bases mean "an abstract base class": with abstract methods only, the interface form as well.
ABC_BASES = {"abc.ABC"}

#: Immutable shapes outside the building blocks: a frozen dataclass, a NamedTuple, an Enum.
ENUM_BASES = {"enum.Enum", "enum.IntEnum", "enum.StrEnum", "enum.Flag", "enum.IntFlag"}
MUTABLE_TYPES = {
    "list",
    "dict",
    "set",
    "bytearray",
    "builtins.list",
    "builtins.dict",
    "builtins.set",
    "builtins.bytearray",
    "collections.deque",
    "collections.defaultdict",
    "collections.OrderedDict",
    "collections.Counter",
    "typing.List",
    "typing.Dict",
    "typing.Set",
    "typing.MutableMapping",
    "typing.MutableSequence",
    "typing.MutableSet",
    "collections.abc.MutableMapping",
    "collections.abc.MutableSequence",
    "collections.abc.MutableSet",
}


@dataclasses.dataclass(frozen=True)
class Place:
    """Where a module sits. `layer` is one of domain, application, incoming, outgoing, adapter, infrastructure, api,
    events, root (the composition root), or None outside every layer."""

    context: str | None = None
    kernel: bool = False
    layer: str | None = None
    shared: bool = False
    sub: str | None = None
    feature: tuple[str, ...] = ()

    @property
    def owner(self) -> str | None:
        return "<kernel>" if self.kernel else self.context


@dataclasses.dataclass
class Import:
    line: int
    module: str
    names: tuple[str, ...]
    absolute: tuple[str, ...]


@dataclasses.dataclass
class Module:
    dotted: str
    path: str
    tree: ast.Module
    place: Place
    is_package: bool
    imports: list[Import] = dataclasses.field(default_factory=list)
    symbols: dict[str, str] = dataclasses.field(default_factory=dict)
    defined: dict[str, ast.AST] = dataclasses.field(default_factory=dict)

    def where(self, node: ast.AST | int) -> str:
        line = node if isinstance(node, int) else getattr(node, "lineno", 1)
        return f"{self.path}:{line}"


@dataclasses.dataclass
class Field:
    """A class-level annotation or a `self.<name>` assignment in any method; `module` is where it is written, which is
    where its annotation resolves and where a finding about it points."""

    name: str
    annotation: ast.expr | None
    line: int
    public: bool
    module: Module


@dataclasses.dataclass
class Klass:
    qualname: str
    name: str
    module: Module
    node: ast.ClassDef
    bases: list[str]
    decorators: list[tuple[str, ast.expr]]
    fields: list[Field]
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]

    @property
    def place(self) -> Place:
        return self.module.place

    @property
    def is_protocol(self) -> bool:
        """The interface form, Java's interface: a `typing.Protocol`, or an `abc.ABC` (or a class with the metaclass
        `abc.ABCMeta`) whose methods are all abstract and that holds no field of its own."""
        if any(b in PROTOCOL for b in self.bases):
            return True
        abstract_base = any(b in ABC_BASES for b in self.bases) or any(
            k.arg == "metaclass" and (dotted_name(k.value) or "").rsplit(".", 1)[-1] == "ABCMeta"
            for k in self.node.keywords
        )
        if not abstract_base or self.fields:
            return False
        return all(
            any((dotted_name(d) or "").rsplit(".", 1)[-1] == "abstractmethod" for d in m.decorator_list)
            for m in self.methods.values()
        )

    def where(self) -> str:
        return self.module.where(self.node)

    def __hash__(self) -> int:
        return hash(self.qualname)


#: Built-in types a call names: `self.items = list(...)` holds a list.
BUILTIN_TYPES = {"list", "dict", "set", "frozenset", "tuple", "int", "str", "float", "bool", "bytes", "bytearray"}


def _assigned_type(value: ast.expr | None, params: dict[str, ast.expr | None]) -> ast.expr | None:
    """The type an assignment to `self.<name>` gives it without an annotation: the annotation of the parameter
    assigned, or the class a call constructs (a capitalised name, or a built-in type)."""
    if isinstance(value, ast.Name):
        return params.get(value.id)
    if isinstance(value, ast.Call):
        name = dotted_name(value.func)
        last = (name or "").rsplit(".", 1)[-1]
        if name and (last[:1].isupper() or name in BUILTIN_TYPES):
            return value.func
    return None


def annotation_expr(node: ast.expr | None) -> ast.expr | None:
    """An annotation, a quoted one parsed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return None
    return node


def dotted_name(node: ast.expr) -> str | None:
    """`a.b.c` of a Name or an Attribute chain, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class Project:
    """Every module below the base package, read once."""

    def __init__(self, layout: DcaLayout) -> None:
        self.layout = layout
        self.problems: list[str] = []
        self.modules: dict[str, Module] = {}
        root = layout.package_dir
        if not root.is_dir():
            raise FileNotFoundError(f"no package {layout.base_package} under {root}")
        self.base = layout.base_package
        for top, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith((".", "__pycache__")))
            for file in sorted(files):
                if not file.endswith(".py"):
                    continue
                path = pathlib.Path(top) / file
                rel = path.relative_to(root).with_suffix("")
                parts = [p for p in rel.parts]
                is_package = parts[-1] == "__init__"
                if is_package:
                    parts = parts[:-1]
                dotted = ".".join([self.base, *parts])
                if self.is_bb(dotted):
                    continue
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
                except SyntaxError as error:
                    self.problems.append(f"{path}: {error}")
                    continue
                shown = os.path.relpath(path, layout.project_root)
                self.modules[dotted] = Module(dotted, shown, tree, Place(), is_package)
        self.contexts = self._contexts()
        for module in self.modules.values():
            module.place = self.place_of(module.dotted)
            self._read_imports(module)
        self.classes: dict[str, Klass] = {}
        for module in self.modules.values():
            self._collect(module, module.tree.body, module.dotted)

    def _collect(self, module: Module, body: list[ast.stmt], prefix: str) -> None:
        """Every class of a module, a nested one as a class of its own: `<module>.Outer.Inner` in a class body,
        `<module>.function.<locals>.Inner` in a function's, as Python's own `__qualname__` names them."""
        for node in body:
            if isinstance(node, ast.ClassDef):
                qualname = f"{prefix}.{node.name}"
                self.classes[qualname] = self._klass(module, node, qualname)
                self._collect(module, node.body, qualname)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._collect(module, node.body, f"{prefix}.{node.name}.<locals>")
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                inner = [
                    *node.body,
                    *getattr(node, "orelse", []),
                    *getattr(node, "finalbody", []),
                    *(s for h in getattr(node, "handlers", []) for s in h.body),
                ]
                self._collect(module, inner, prefix)

    # --- places ------------------------------------------------------------------------------------------------

    def _contexts(self) -> dict[str, ast.Call | None]:
        """{context package name: its `__dca__ = BoundedContext(...)` call, or None when undeclared}."""
        layout = self.layout
        found: dict[str, ast.Call | None] = {}
        for dotted, module in self.modules.items():
            parts = dotted[len(self.base) + 1 :].split(".") if dotted != self.base else []
            if len(parts) != 1 or not module.is_package:
                continue
            name = parts[0]
            if name in (layout.shared_kernel, layout.infrastructure):
                continue
            declaration = self.declaration(module)
            has_layer = any(
                f"{dotted}.{layer}" in self.modules for layer in (layout.domain, layout.application, layout.adapter)
            )
            if (
                declaration is not None
                and dotted_name(declaration.func)
                and (dotted_name(declaration.func) or "").endswith("BoundedContext")
            ):
                found[name] = declaration
            elif has_layer:
                found[name] = None
        return found

    @staticmethod
    def declaration(module: Module) -> ast.Call | None:
        for node in module.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(t, ast.Name) and t.id == "__dca__" for t in targets) and isinstance(
                    node.value, ast.Call
                ):
                    return node.value
        return None

    def module_markers(self, marker: str) -> list[tuple[Module, ast.Call]]:
        """(module, its `__dca__ = <marker>()` call) for every module that declares the building block `marker` as a
        module: an open host service of functions marks its package so, as a context marks its own."""
        out = []
        for module in self.modules.values():
            call = self.declaration(module)
            if call is not None and self.resolve(module, call.func) == f"{BB}.{marker}":
                out.append((module, call))
        return out

    @functools.cached_property
    def holds_production_code(self) -> bool:
        """Whether a module below the base package holds production code: a statement besides its docstring, in a
        module that is not a program entry point (`is_entry_point`). An empty `__init__.py`, or one with a docstring
        alone, is no production code yet, nor is the `main` a project generator writes; tests outside the package
        are not read, tests inside it count."""
        for module in self.modules.values():
            body = module.tree.body
            if body and ast.get_docstring(module.tree, clean=False) is not None:
                body = body[1:]
            if body and not is_entry_point(module):
                return True
        return False

    def declared_contexts(self) -> dict[str, str]:
        """{package: declared name} of the contexts that carry a BoundedContext declaration."""
        out = {}
        for package, call in self.contexts.items():
            if call is None:
                continue
            name = keyword(call, "name", 0)
            out[package] = name if isinstance(name, str) else package
        return out

    def place_of(self, dotted: str) -> Place:
        layout = self.layout
        if dotted != self.base and not dotted.startswith(self.base + "."):
            return Place()
        parts = dotted[len(self.base) + 1 :].split(".") if dotted != self.base else []
        if not parts:
            return Place()
        head, rest = parts[0], parts[1:]
        if head == layout.infrastructure:
            return Place(layer="root")
        kernel = head == layout.shared_kernel
        if not kernel and head not in self.contexts:
            return Place()
        context = None if kernel else head
        if not rest:
            return Place(context=context, kernel=kernel)
        layer, below = rest[0], rest[1:]
        if layer == layout.domain:
            return Place(context, kernel, "domain")
        if layer == layout.application:
            shared = bool(below) and below[0] == layout.shared
            grouped = list(below)
            while grouped and grouped[0] in layout.operation_containers:
                grouped.pop(0)
            feature = () if shared else tuple(grouped)
            return Place(context, kernel, "application", shared=shared, feature=feature)
        if layer == layout.adapter:
            if below and below[0] == layout.incoming:
                sub = below[1] if len(below) > 1 and below[1] in (layout.event, layout.web) else None
                return Place(context, kernel, "incoming", sub=sub, feature=tuple(below[1:]))
            if below and below[0] == layout.outgoing:
                return Place(context, kernel, "outgoing", feature=tuple(below[1:]))
            return Place(context, kernel, "adapter")
        if layer == layout.infrastructure:
            return Place(context, kernel, "infrastructure")
        if layer == layout.api:
            return Place(context, kernel, "api")
        if layer == layout.events:
            # Beside api, as Java keeps {context}/events beside {context}/api: a consumer of the events depends on
            # the contract alone. The kernel has no events package; DCA-STR-007 reports one.
            return Place(context, kernel, "events")
        return Place(context, kernel)

    # --- imports and names -------------------------------------------------------------------------------------

    def _read_imports(self, module: Module) -> None:
        package = module.dotted if module.is_package else module.dotted.rpartition(".")[0]
        for node in module.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                module.defined[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        module.defined[target.id] = node
            elif isinstance(node, (ast.AnnAssign, ast.TypeAlias)):
                target = node.target if isinstance(node, ast.AnnAssign) else node.name
                if isinstance(target, ast.Name):
                    module.defined[target.id] = node
        for statement in ast.walk(module.tree):
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    module.imports.append(Import(statement.lineno, alias.name, (), (alias.name,)))
                    local = alias.asname or alias.name.split(".")[0]
                    module.symbols.setdefault(local, alias.name if alias.asname else alias.name.split(".")[0])
            elif isinstance(statement, ast.ImportFrom):
                if statement.level:
                    anchor = package.split(".")
                    if statement.level > 1:
                        anchor = anchor[: len(anchor) - (statement.level - 1)]
                    source = ".".join(anchor + ([statement.module] if statement.module else []))
                else:
                    source = statement.module or ""
                names = tuple(a.name for a in statement.names)
                module.imports.append(Import(statement.lineno, source, names, tuple(f"{source}.{n}" for n in names)))
                for alias in statement.names:
                    module.symbols.setdefault(alias.asname or alias.name, f"{source}.{alias.name}")

    def import_targets(self, module: Module) -> Iterator[tuple[int, str]]:
        """(line, module) for every import: an imported submodule by its own name, else the module imported from."""
        for item in module.imports:
            if not item.names:
                yield item.line, item.module
                continue
            subs = [a for a in item.absolute if a in self.modules]
            if subs:
                yield from ((item.line, s) for s in subs)
            if len(subs) < len(item.names):
                yield item.line, item.module

    def is_project(self, dotted: str) -> bool:
        return (dotted == self.base or dotted.startswith(self.base + ".")) and not self.is_bb(dotted)

    @staticmethod
    def is_stdlib(dotted: str) -> bool:
        return dotted.split(".")[0] in STDLIB

    def is_bb(self, dotted: str) -> bool:
        """The building blocks, or a module the layout names as their copy."""
        return any(dotted == b or dotted.startswith(b + ".") for b in (BB, *self.layout.building_blocks))

    def is_framework(self, dotted: str) -> bool:
        return any(dotted == f or dotted.startswith(f + ".") for f in self.layout.frameworks)

    def resolve(self, module: Module, node: ast.expr) -> str | None:
        """The qualified name an expression names in a module, re-exports followed."""
        name = dotted_name(node)
        if name is None:
            return None
        head, _, tail = name.partition(".")
        if head in module.symbols:
            full = module.symbols[head] + (f".{tail}" if tail else "")
        elif head in module.defined:
            full = f"{module.dotted}.{name}"
        else:
            full = f"builtins.{name}" if hasattr(builtins, head) else name
        return self.canonical(full)

    @functools.cache  # noqa: B019 - one project, read once
    def canonical(self, full: str) -> str:
        if self.is_bb(full):
            return f"{BB}.{full.rsplit('.', 1)[-1]}"
        seen = set()
        while full not in self.classes_by_name() and full not in seen:
            seen.add(full)
            owner, _, attr = full.rpartition(".")
            module = self.modules.get(owner)
            if module is None or attr not in module.symbols:
                break
            full = module.symbols[attr]
            if self.is_bb(full):
                return f"{BB}.{full.rsplit('.', 1)[-1]}"
        return full

    def classes_by_name(self) -> dict[str, Klass]:
        return getattr(self, "classes", {})

    def klass(self, module: Module, node: ast.expr) -> Klass | None:
        name = self.resolve(module, node)
        return self.classes.get(name) if name else None

    def refs(self, module: Module, node: ast.AST | None) -> Iterator[tuple[ast.expr, str]]:
        """Every name an expression or a statement mentions, resolved; an attribute chain once, outermost;
        quoted annotations read."""
        if node is None:
            return
        inner: set[int] = set()
        for item in ast.walk(node):
            if isinstance(item, ast.Constant) and isinstance(item.value, str) and item.value[:1].isupper():
                parsed = annotation_expr(item)
                if parsed is not None and parsed is not item:
                    yield from self.refs(module, parsed)
                continue
            if id(item) in inner or not isinstance(item, (ast.Name, ast.Attribute)):
                continue
            if isinstance(item, ast.Attribute):
                sub: ast.expr = item.value
                while isinstance(sub, ast.Attribute):
                    inner.add(id(sub))
                    sub = sub.value
                inner.add(id(sub))
            name = self.resolve(module, item)
            if name:
                yield item, name

    def type_classes(self, module: Module, annotation: ast.expr | None) -> list[Klass]:
        """The project classes an annotation names, through generic arguments."""
        return [self.classes[n] for _, n in self.refs(module, annotation_expr(annotation)) if n in self.classes]

    def type_names(self, module: Module, annotation: ast.expr | None) -> list[str]:
        return [n for _, n in self.refs(module, annotation_expr(annotation))]

    # --- classes and roles -------------------------------------------------------------------------------------

    def _klass(self, module: Module, node: ast.ClassDef, qualname: str) -> Klass:
        bases = []
        for base in node.bases:
            base = base.value if isinstance(base, ast.Subscript) else base
            name = dotted_name(base)
            if name:
                bases.append(name)
        decorators = []
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = dotted_name(target)
            if name:
                decorators.append((name, decorator))
        fields: list[Field] = []
        methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if "ClassVar" in ast.unparse(item.annotation):
                    continue
                fields.append(
                    Field(item.target.id, item.annotation, item.lineno, not item.target.id.startswith("_"), module)
                )
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[item.name] = item
        known = {f.name for f in fields}
        # `__init__` first, then every other method: a field is where the object first holds it.
        ordered = sorted(methods.values(), key=lambda m: m.name != "__init__")
        for method in ordered:
            params = {a.arg: a.annotation for a in method.args.args + method.args.kwonlyargs}
            for stmt in ast.walk(method):
                targets: list[ast.expr] = []
                annotation: ast.expr | None = None
                if isinstance(stmt, ast.Assign):
                    targets = stmt.targets
                elif isinstance(stmt, ast.AnnAssign):
                    targets, annotation = [stmt.target], stmt.annotation
                for target in targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                        and target.attr not in known
                    ):
                        typed = annotation or _assigned_type(getattr(stmt, "value", None), params)
                        known.add(target.attr)
                        fields.append(
                            Field(
                                target.attr, typed, getattr(stmt, "lineno", 1), not target.attr.startswith("_"), module
                            )
                        )
        klass = Klass(qualname, node.name, module, node, [], [], fields, methods)
        klass.bases = [self._resolve_late(module, b) for b in bases]
        klass.decorators = [(self._resolve_late(module, n), d) for n, d in decorators]
        return klass

    def _resolve_late(self, module: Module, name: str) -> str:
        head, _, tail = name.partition(".")
        if head in module.symbols:
            full = module.symbols[head] + (f".{tail}" if tail else "")
        elif head in module.defined:
            full = f"{module.dotted}.{name}"
        else:
            full = f"builtins.{name}" if hasattr(builtins, head) else name
        if self.is_bb(full):
            return f"{BB}.{full.rsplit('.', 1)[-1]}"
        return full

    def base_classes(self, klass: Klass) -> list[Klass]:
        out = []
        for base in klass.bases:
            found = self.classes.get(self.canonical(base))
            if found is not None and found is not klass:
                out.append(found)
        return out

    def roles(self, klass: Klass) -> frozenset[str]:
        """The building blocks a class carries, through its bases and the building blocks' own hierarchy."""
        return self._roles(klass.qualname, frozenset())

    def _roles(self, qualname: str, seen: frozenset[str]) -> frozenset[str]:
        klass = self.classes.get(qualname)
        if klass is None or qualname in seen:
            return frozenset()
        found: set[str] = set()
        for base in klass.bases:
            base = self.canonical(base)
            if base.startswith(BB + "."):
                found |= bb_closure(base.rsplit(".", 1)[-1])
            else:
                found |= self._roles(base, seen | {qualname})
        return frozenset(found)

    def ancestors(self, klass: Klass) -> set[str]:
        """Every qualified base name, transitively, the project's and outside ones."""
        out: set[str] = set()
        todo = [klass]
        while todo:
            current = todo.pop()
            for base in current.bases:
                base = self.canonical(base)
                if base not in out:
                    out.add(base)
                    if base in self.classes:
                        todo.append(self.classes[base])
        return out

    def lineage(self, klass: Klass) -> list[Klass]:
        """The project classes a class extends, transitively, nearest first."""
        out: list[Klass] = []
        todo = list(self.base_classes(klass))
        while todo:
            current = todo.pop(0)
            if current is klass or current in out:
                continue
            out.append(current)
            todo += self.base_classes(current)
        return out

    def members(self, klass: Klass) -> list[Klass]:
        """The class and the project bases it extends that carry no building block, transitively: their fields and
        methods are the class's own as far as a rule over it goes. A base that carries a role is selected, and
        checked, by itself."""
        return [klass, *(b for b in self.lineage(klass) if not self.roles(b))]

    def member_fields(self, klass: Klass) -> list[Field]:
        """The fields of the class and of its role-less bases, a name once, the nearest declaration."""
        out: dict[str, Field] = {}
        for owner in self.members(klass):
            for field in owner.fields:
                out.setdefault(field.name, field)
        return list(out.values())

    def member_methods(self, klass: Klass) -> list[tuple[Klass, str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        """(owner, name, method) for the methods of the class and of its role-less bases, an override once."""
        out: dict[str, tuple[Klass, str, ast.FunctionDef | ast.AsyncFunctionDef]] = {}
        for owner in self.members(klass):
            for name, method in owner.methods.items():
                out.setdefault(name, (owner, name, method))
        return list(out.values())

    def all_fields(self, klass: Klass) -> list[Field]:
        """The fields of the class and of every project class it extends, a name once: what `self.<name>` holds."""
        out: dict[str, Field] = {}
        for owner in [klass, *self.lineage(klass)]:
            for field in owner.fields:
                out.setdefault(field.name, field)
        return list(out.values())

    def has(self, klass: Klass, role: str) -> bool:
        return role in self.roles(klass)

    def with_role(self, role: str) -> list[Klass]:
        return [k for k in self.classes.values() if self.has(k, role)]

    def is_frozen_dataclass(self, klass: Klass) -> bool:
        for name, decorator in klass.decorators:
            if (
                name.endswith("dataclass")
                and isinstance(decorator, ast.Call)
                and any(
                    k.arg == "frozen" and isinstance(k.value, ast.Constant) and k.value.value is True
                    for k in decorator.keywords
                )
            ):
                return True
        return bool(self.roles(klass) & {"Value", "DomainEvent", "IntegrationEvent"})

    def is_dataclass(self, klass: Klass) -> ast.expr | None:
        for name, decorator in klass.decorators:
            if name in ("dataclasses.dataclass", "dataclass") or name.endswith(".dataclass"):
                return decorator
        return None

    def is_immutable_shape(self, klass: Klass) -> bool:
        """A frozen dataclass (by decorator or by its base), a NamedTuple or an Enum."""
        ancestors = self.ancestors(klass)
        return (
            self.is_frozen_dataclass(klass)
            or "typing.NamedTuple" in ancestors
            or bool(ancestors & ENUM_BASES)
            or any(self.is_frozen_dataclass(b) for b in self.base_classes(klass))
        )

    def mutable_fields(self, klass: Klass) -> list[Field]:
        """Fields whose type is a mutable collection (list, dict, set, ...), the shallow part of immutability; the
        fields of role-less bases included."""
        out = []
        for field in self.member_fields(klass):
            names = set(self.type_names(field.module, field.annotation))
            if names & MUTABLE_TYPES:
                out.append(field)
        return out

    def mutators(self, klass: Klass) -> list[tuple[str, ast.AST, Module]]:
        """(method, node, its module) for the methods other than `__init__`/`__post_init__` that assign to
        `self.<attr>` - directly or through a local alias of `self` - or call `object.__setattr__`, and a
        `__setattr__` of its own; the methods of role-less bases included."""
        out: list[tuple[str, ast.AST, Module]] = []
        for owner, name, method in self.member_methods(klass):
            if name in ("__init__", "__post_init__", "__new__"):
                continue
            if name == "__setattr__":
                out.append((name, method, owner.module))
                continue
            selves = {"self"}
            for node in ast.walk(method):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in selves:
                    selves.update(t.id for t in node.targets if isinstance(t, ast.Name))
            for node in ast.walk(method):
                targets: list[ast.expr] = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                    targets = [node.target]
                if any(
                    isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in selves
                    for t in targets
                ):
                    out.append((name, node, owner.module))
                    break
                if isinstance(node, ast.Call) and dotted_name(node.func) == "object.__setattr__":
                    out.append((name, node, owner.module))
                    break
        return out

    def name_roles(self, name: str) -> frozenset[str]:
        """The roles a qualified name carries: a building block's own, or a project class's."""
        if name.startswith(BB + "."):
            return bb_closure(name.rsplit(".", 1)[-1])
        klass = self.classes.get(name)
        return self.roles(klass) if klass is not None else frozenset()

    def self_types(self, klass: Klass) -> dict[str, frozenset[str]]:
        """{attribute: the roles its annotation names} for `self.<attribute>`, the attributes a base holds included."""
        out: dict[str, frozenset[str]] = {}
        for field in self.all_fields(klass):
            roles: frozenset[str] = frozenset()
            for name in self.type_names(field.module, field.annotation):
                roles |= self.name_roles(name)
            out[field.name] = roles
        return out

    def scope_types(self, klass: Klass | None, module: Module, scope: ast.AST) -> dict[str, frozenset[str]]:
        """{local name: the roles it holds} in a function or method, nested functions included: a parameter or a
        local annotated with a role, a local bound to `self.<attribute>` or to another such name (an alias)."""
        fields = self.self_types(klass) if klass is not None else {}
        out: dict[str, frozenset[str]] = {}

        def typed(annotation: ast.expr | None) -> frozenset[str]:
            roles: frozenset[str] = frozenset()
            for name in self.type_names(module, annotation):
                roles |= self.name_roles(name)
            return roles

        for node in ast.walk(scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for argument in parameters(node):
                    roles = typed(argument.annotation)
                    if roles:
                        out[argument.arg] = roles
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                roles = typed(node.annotation)
                if roles:
                    out[node.target.id] = roles
        changed = True
        while changed:
            changed = False
            for node in ast.walk(scope):
                if not isinstance(node, (ast.Assign, ast.NamedExpr)):
                    continue
                value = node.value
                held: frozenset[str] = frozenset()
                if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.value.id == "self":
                    held = fields.get(value.attr, frozenset())
                elif isinstance(value, ast.Name):
                    held = out.get(value.id, frozenset())
                if not held:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and out.get(target.id) != held:
                        out[target.id] = held
                        changed = True
        return out

    def calls(self, klass: Klass, method: ast.AST) -> Iterator[tuple[ast.Call, str, frozenset[str]]]:
        """(call, method name, the roles of its receiver) for every call on `self.<attr>` - an attribute of the class
        or of a base - and on a local that holds a role: a typed parameter or local, or an alias of one."""
        types = self.self_types(klass)
        names = self.scope_types(klass, klass.module, method)
        for node in ast.walk(method):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                receiver = node.func.value
                if (
                    isinstance(receiver, ast.Attribute)
                    and isinstance(receiver.value, ast.Name)
                    and receiver.value.id == "self"
                ):
                    yield node, node.func.attr, types.get(receiver.attr, frozenset())
                elif isinstance(receiver, ast.Name) and receiver.id in names:
                    yield node, node.func.attr, names[receiver.id]

    def constructions(self, module: Module, node: ast.AST | None = None) -> Iterator[tuple[ast.Call, Klass]]:
        """Every call of a project class (a construction), in a module or below a node."""
        for item in ast.walk(node if node is not None else module.tree):
            if isinstance(item, ast.Call):
                klass = self.klass(module, item.func)
                if klass is not None:
                    yield item, klass

    # --- views -------------------------------------------------------------------------------------------------

    def in_layer(self, *layers: str) -> list[Module]:
        return [m for m in self.modules.values() if m.place.layer in layers]

    def classes_in(self, *layers: str) -> list[Klass]:
        return [k for k in self.classes.values() if k.place.layer in layers]


def bb_closure(name: str) -> frozenset[str]:
    out = {name}
    for parent in BB_PARENTS.get(name, ()):
        out |= bb_closure(parent)
    return frozenset(out)


def keyword(call: ast.Call, name: str, position: int | None = None) -> object:
    """A literal argument of a declaration call, by keyword or position; an enum member as `Enum.MEMBER`; a tuple
    or list as a list."""
    node: ast.expr | None = None
    for item in call.keywords:
        if item.arg == name:
            node = item.value
    if node is None and position is not None and len(call.args) > position:
        node = call.args[position]
    return literal(node)


def literal(node: ast.expr | None) -> object:
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return [literal(e) for e in node.elts]
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return node
    return None


def functions(node: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for item in ast.walk(node):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield item


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def public(name: str) -> bool:
    return not name.startswith("_")


def parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    args = function.args
    found = args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]
    return [a for a in found if a.arg not in ("self", "cls")]


def is_entry_point(module: Module) -> bool:
    """Whether the module only starts the program - the shape a project generator writes before any production code
    exists. Its statements are a docstring, imports, at most one function named `main`, and the guard
    `if __name__ == "__main__":` whose body only calls (expression statements) or raises (`raise SystemExit(...)`);
    a module named `__main__`, which runs only as the program, may call or raise at the top level as well. Every
    other statement - a class, a second function, an assignment - makes it production code."""
    main_module = module.dotted.rpartition(".")[2] == "__main__"
    functions = 0
    for node in module.tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main":
            functions += 1
            continue
        if _is_main_guard(node) or (main_module and _only_starts(node)):
            continue
        return False
    return functions <= 1


def _is_main_guard(node: ast.stmt) -> bool:
    """`if __name__ == "__main__":` with no else, whose body only calls or raises."""
    if not isinstance(node, ast.If) or node.orelse:
        return False
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
        and all(_only_starts(statement) for statement in node.body)
    )


def _only_starts(node: ast.stmt) -> bool:
    """A call as a statement (`main()`, `sys.exit(main())`) or a raise (`raise SystemExit(main())`)."""
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)) or isinstance(node, ast.Raise)
