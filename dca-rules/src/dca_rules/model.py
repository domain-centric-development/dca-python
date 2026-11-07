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
    "InputPortException": ("PortException",),
    "UseCaseException": ("InputPortException",),
    "OutputPortException": ("PortException",),
}

STDLIB = frozenset(sys.stdlib_module_names) | {"__future__"}

#: Where a class's bases mean "a protocol".
PROTOCOL = {"typing.Protocol", "typing_extensions.Protocol"}

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
    root (the composition root), or None outside every layer."""

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
    name: str
    annotation: ast.expr | None
    line: int
    public: bool


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
        return any(b in PROTOCOL for b in self.bases)

    def where(self) -> str:
        return self.module.where(self.node)

    def __hash__(self) -> int:
        return hash(self.qualname)


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
            for node in module.tree.body:
                if isinstance(node, ast.ClassDef):
                    self.classes[f"{module.dotted}.{node.name}"] = self._klass(module, node)

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
            feature = () if shared else tuple(below)
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
            sub = "events" if below and below[0] == layout.events else None
            return Place(context, kernel, "api", sub=sub)
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

    def _klass(self, module: Module, node: ast.ClassDef) -> Klass:
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
                fields.append(Field(item.target.id, item.annotation, item.lineno, not item.target.id.startswith("_")))
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[item.name] = item
        init = methods.get("__init__")
        if init is not None:
            params = {a.arg: a.annotation for a in init.args.args + init.args.kwonlyargs}
            known = {f.name for f in fields}
            for stmt in ast.walk(init):
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
                        value = getattr(stmt, "value", None)
                        if annotation is None and isinstance(value, ast.Name):
                            annotation = params.get(value.id)
                        known.add(target.attr)
                        fields.append(
                            Field(target.attr, annotation, getattr(stmt, "lineno", 1), not target.attr.startswith("_"))
                        )
        klass = Klass(f"{module.dotted}.{node.name}", node.name, module, node, [], [], fields, methods)
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
        """Fields whose type is a mutable collection (list, dict, set, ...), the shallow part of immutability."""
        out = []
        for field in klass.fields:
            names = set(self.type_names(klass.module, field.annotation))
            if names & MUTABLE_TYPES:
                out.append(field)
        return out

    def mutators(self, klass: Klass) -> list[tuple[str, ast.AST]]:
        """Methods other than `__init__`/`__post_init__` that assign to `self.<attr>` or call `object.__setattr__`,
        and a `__setattr__` of its own."""
        out: list[tuple[str, ast.AST]] = []
        for name, method in klass.methods.items():
            if name in ("__init__", "__post_init__", "__new__"):
                continue
            if name == "__setattr__":
                out.append((name, method))
                continue
            for node in ast.walk(method):
                targets: list[ast.expr] = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                    targets = [node.target]
                if any(
                    isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
                    for t in targets
                ):
                    out.append((name, node))
                    break
                if isinstance(node, ast.Call) and dotted_name(node.func) == "object.__setattr__":
                    out.append((name, node))
                    break
        return out

    def name_roles(self, name: str) -> frozenset[str]:
        """The roles a qualified name carries: a building block's own, or a project class's."""
        if name.startswith(BB + "."):
            return bb_closure(name.rsplit(".", 1)[-1])
        klass = self.classes.get(name)
        return self.roles(klass) if klass is not None else frozenset()

    def self_types(self, klass: Klass) -> dict[str, frozenset[str]]:
        """{attribute: the roles its annotation names} for `self.<attribute>`."""
        out: dict[str, frozenset[str]] = {}
        for field in klass.fields:
            roles: frozenset[str] = frozenset()
            for name in self.type_names(klass.module, field.annotation):
                roles |= self.name_roles(name)
            out[field.name] = roles
        return out

    def calls(self, klass: Klass, method: ast.AST) -> Iterator[tuple[ast.Call, str, frozenset[str]]]:
        """(call, method name, the roles of its receiver) for every `self.<attr>.<method>(...)` call."""
        types = self.self_types(klass)
        for node in ast.walk(method):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                receiver = node.func.value
                if (
                    isinstance(receiver, ast.Attribute)
                    and isinstance(receiver.value, ast.Name)
                    and receiver.value.id == "self"
                ):
                    yield node, node.func.attr, types.get(receiver.attr, frozenset())

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
