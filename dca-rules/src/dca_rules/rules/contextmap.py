"""Context map rules: the relationships a context declares in `__dca__`, against each other and against the imports."""

from __future__ import annotations

import ast
import dataclasses

from dca_rules.model import BB, Module, Project, keyword
from dca_rules.rules import Checked, Finding, project_imports, rule

RELATIONSHIPS = ("Upstream", "ExternalUpstream", "Partnership")


@dataclasses.dataclass
class Declared:
    package: str
    name: str
    module: Module
    upstreams: list[ast.Call]
    externals: list[ast.Call]
    partnerships: list[ast.Call]


def calls(value: object) -> list[ast.Call]:
    return [c for c in value if isinstance(c, ast.Call)] if isinstance(value, list) else []


def declared(p: Project) -> dict[str, Declared]:
    """{declared name: its declaration}."""
    out = {}
    for package, call in p.contexts.items():
        if call is None:
            continue
        module = p.modules[f"{p.base}.{package}"]
        name = keyword(call, "name", 0)
        name = name if isinstance(name, str) else package
        out[name] = Declared(
            package,
            name,
            module,
            calls(keyword(call, "upstreams")),
            calls(keyword(call, "external_upstreams")),
            calls(keyword(call, "partnerships")),
        )
    return out


def text(call: ast.Call, name: str, position: int | None = None) -> str:
    value = keyword(call, name, position)
    return value if isinstance(value, str) else ""


def members(call: ast.Call, name: str) -> list[str]:
    value = keyword(call, name)
    if isinstance(value, list):
        return [str(v).lower() for v in value if isinstance(v, str)]
    return [value.lower()] if isinstance(value, str) else []


def translation(call: ast.Call) -> str:
    value = keyword(call, "translation", 1)
    return str(value).lower() if isinstance(value, str) else ""


def planned(call: ast.Call) -> bool:
    return str(keyword(call, "status")).upper() == "PLANNED"


def channel_of(p: Project, place_layer: str | None, sub: str | None) -> str | None:
    if place_layer != "api":
        return None
    return "events" if sub == "events" else "api"


def edges(p: Project) -> list[tuple[Module, int, str, str, str]]:
    """(module, line, from package, to package, channel) for every import into another context's api."""
    out = []
    for module in p.modules.values():
        if module.place.context is None:
            continue
        for line, _target, place in project_imports(p, module):
            channel = channel_of(p, place.layer, place.sub)
            if place.context and place.context != module.place.context and channel:
                out.append((module, line, module.place.context, place.context, channel))
    return out


@rule("DCA-MAP-001")
def map_001(p: Project) -> Checked:
    """Selects every relationship the source declares, wherever it sits."""
    homes = {d.module.dotted for d in declared(p).values()}
    found = []
    selected = 0
    for module in p.modules.values():
        for call, name in ((n, p.resolve(module, n.func)) for n in ast.walk(module.tree) if isinstance(n, ast.Call)):
            if name not in {f"{BB}.{r}" for r in RELATIONSHIPS}:
                continue
            selected += 1
            if module.dotted not in homes:
                found.append(
                    Finding(
                        module.where(call),
                        f"{module.dotted} declares a {name.rsplit('.', 1)[-1]} outside a bounded context's declaration",
                    )
                )
    return Checked(selected, found)


@rule("DCA-MAP-002")
def map_002(p: Project) -> Checked:
    found = []
    contexts = declared(p)
    for d in contexts.values():
        seen = set()
        for call in d.externals:
            name, interaction = text(call, "name", 0), str(keyword(call, "interaction", 2))
            if not name.strip() or name in contexts:
                found.append(
                    Finding(
                        d.module.where(call),
                        f"{d.name} declares the external upstream {name!r}, blank or a context's name",
                    )
                )
            if (name, interaction) in seen:
                found.append(Finding(d.module.where(call), f"{d.name} declares {name} {interaction} twice"))
            seen.add((name, interaction))
    return Checked(sum(len(d.externals) for d in contexts.values()), found)


def _upstreams(contexts: dict[str, Declared]) -> int:
    return sum(len(d.upstreams) for d in contexts.values())


@rule("DCA-MAP-004")
def map_004(p: Project) -> Checked:
    contexts = declared(p)
    return Checked(
        _upstreams(contexts),
        [
            Finding(
                d.module.where(c),
                f"{d.name} declares the upstream {text(c, 'context', 0)!r}, which is itself or no context",
            )
            for d in contexts.values()
            for c in d.upstreams
            if text(c, "context", 0) not in contexts or text(c, "context", 0) == d.name
        ],
    )


@rule("DCA-MAP-005")
def map_005(p: Project) -> Checked:
    found = []
    contexts = declared(p)
    for d in contexts.values():
        seen = set()
        for call in d.upstreams:
            target, via = text(call, "context", 0), members(call, "via")
            if not via:
                found.append(Finding(d.module.where(call), f"{d.name} declares the upstream {target} via nothing"))
            for channel in via:
                if (target, channel) in seen:
                    found.append(Finding(d.module.where(call), f"{d.name} declares {target} via {channel} twice"))
                seen.add((target, channel))
    return Checked(_upstreams(contexts), found)


@rule("DCA-MAP-007")
def map_007(p: Project) -> Checked:
    contexts = declared(p)
    used = {(src, dst, ch) for _m, _l, src, dst, ch in edges(p)}
    found = []
    for d in contexts.values():
        for call in d.upstreams:
            target = contexts.get(text(call, "context", 0))
            if target is None or planned(call):
                continue
            for channel in members(call, "via"):
                if (d.package, target.package, channel) not in used:
                    found.append(
                        Finding(
                            d.module.where(call),
                            f"{d.name} declares {target.name} via {channel}; no module of it uses that channel",
                        )
                    )
    return Checked(_upstreams(contexts), found)


def _upstream(contexts: dict[str, Declared], src: str, dst: str) -> ast.Call | None:
    by_package = {d.package: d for d in contexts.values()}
    source, target = by_package.get(src), by_package.get(dst)
    if source is None or target is None:
        return None
    return next((c for c in source.upstreams if text(c, "context", 0) == target.name), None)


@rule("DCA-MAP-008")
def map_008(p: Project) -> Checked:
    """Selects the imports into another context's api."""
    contexts = declared(p)
    found = []
    selected = edges(p)
    for module, line, src, dst, channel in selected:
        call = _upstream(contexts, src, dst)
        if call is None or ("acl" not in translation(call) and "anti" not in translation(call)):
            continue
        wanted = "outgoing" if channel == "api" else "incoming"
        if module.place.layer != wanted:
            found.append(
                Finding(
                    module.where(line),
                    f"{module.dotted} uses the {channel} of {dst}; behind an "
                    f"anti-corruption layer only the {wanted} adapter does",
                )
            )
    return Checked(len(selected), found)


@rule("DCA-MAP-009")
def map_009(p: Project) -> Checked:
    """Selects the imports into another context's api."""
    contexts = declared(p)
    selected = edges(p)
    return Checked(
        len(selected),
        [
            Finding(m.where(line), f"{m.dotted} lets the contract of {dst} into the domain")
            for m, line, src, dst, _ch in selected
            if m.place.layer == "domain"
            and (c := _upstream(contexts, src, dst)) is not None
            and "conformist" in translation(c)
        ],
    )


@rule("DCA-MAP-010")
def map_010(p: Project) -> Checked:
    found = []
    contexts = declared(p)
    for d in contexts.values():
        for call in d.externals:
            listed = keyword(call, "contract_packages")
            packages = [v for v in listed if isinstance(v, str)] if isinstance(listed, list) else []
            if not packages:
                continue
            outbound = "OUTBOUND" in str(keyword(call, "interaction", 2)).upper()
            acl = "conformist" not in translation(call)
            for module in p.modules.values():
                if module.place.context != d.package:
                    continue
                for line, target in p.import_targets(module):
                    if not any(target == c or target.startswith(c + ".") for c in packages):
                        continue
                    wanted = "outgoing" if outbound else "incoming"
                    if (acl and module.place.layer != wanted) or (not acl and module.place.layer == "domain"):
                        found.append(
                            Finding(
                                module.where(line),
                                f"{module.dotted} uses the contract {target} of "
                                f"{text(call, 'name', 0)} outside the {wanted} adapter",
                            )
                        )
    return Checked(sum(len(d.externals) for d in contexts.values()), found)


@rule("DCA-MAP-011")
def map_011(p: Project) -> Checked:
    """Selects the imports into another context's api."""
    contexts = declared(p)
    by_package = {d.package: d for d in contexts.values()}
    found = []
    selected = edges(p)
    for module, line, src, dst, channel in selected:
        call = _upstream(contexts, src, dst)
        if call is None or channel not in members(call, "via"):
            name = by_package[dst].name if dst in by_package else dst
            found.append(
                Finding(
                    module.where(line),
                    f"{module.dotted} uses the {channel} of {name} without an "
                    f"Upstream(context={name!r}, via=(...{channel.upper()},)) declaration",
                )
            )
    return Checked(len(selected), found)


@rule("DCA-MAP-012")
def map_012(p: Project) -> Checked:
    contexts = declared(p)
    found = []
    for d in contexts.values():
        for call in d.partnerships:
            other = text(call, "context", 0)
            if other not in contexts or other == d.name:
                found.append(
                    Finding(
                        d.module.where(call), f"{d.name} declares a partnership with {other!r}, itself or no context"
                    )
                )
            elif not any(text(c, "context", 0) == d.name for c in contexts[other].partnerships):
                found.append(
                    Finding(
                        d.module.where(call),
                        f"{d.name} declares a partnership with {other}, which does not declare it back",
                    )
                )
    return Checked(sum(len(d.partnerships) for d in contexts.values()), found)


@rule("DCA-MAP-013")
def map_013(p: Project) -> Checked:
    found = []
    for d in declared(p).values():
        for call in d.upstreams:
            found.append(
                Finding(
                    d.module.where(call),
                    f"{d.name} -> {text(call, 'context', 0)} "
                    f"({translation(call)}, via {', '.join(members(call, 'via'))})",
                )
            )
        for call in d.externals:
            found.append(Finding(d.module.where(call), f"{d.name} -> external {text(call, 'name', 0)}"))
        for call in d.partnerships:
            found.append(Finding(d.module.where(call), f"{d.name} <-> {text(call, 'context', 0)}"))
    return Checked(len(found), found)
