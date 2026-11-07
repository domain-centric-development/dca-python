"""Writes rules.json for DCA-Python: every DCA rule id with its meaning in Python.

Usage: python3 map_rules.py <path to dca-java/rules.json> <output rules.json>

Titles and rationales come from the Java catalogue, so an id keeps one meaning; selects and checks say how Python
holds the rule. Which ids the suite implements is read from the suite itself (`dca_rules.rules.implemented()`),
so the script runs inside the workspace's environment. Each entry carries a category and the levels that hold it:

  category     type-checker | linter | ast-test | reformulated | n/a
  enforcement  imports   - an ast test over the import statements, function-level and TYPE_CHECKING imports included
               source    - an ast test over the declarations: classes, bases, fields, signatures, calls
               runtime   - a building block refuses at class creation (a frozen dataclass by its base, an integration
                           event without its type)
               mypy      - the type checker the profile names (mypy --strict by default) over a bound or a Protocol
               ruff      - a ruff rule in a per-directory ruff.toml (banned-api)
"""

from __future__ import annotations

import json
import sys

# The layout the selections speak about (see dca_rules/layout.py): <base>.<context>.{domain, application[.shared],
# adapter.incoming[.event|.web], adapter.outgoing, infrastructure, api[.events]}, <base>.sharedkernel,
# <base>.infrastructure (the composition root). A role is a building block named among a class's bases, transitively.
LAYOUT = {
    "declaration": "[tool.dca] in pyproject.toml; a context: __dca__ = BoundedContext(...) in its __init__.py",
    "layers": ["domain", "application", "adapter.incoming", "adapter.outgoing", "infrastructure", "api"],
    "applicationShared": "shared",
    "adapterModules": {"incoming": "adapter.incoming", "outgoing": "adapter.outgoing", "event": "event", "web": "web"},
    "apiModules": {"api": "api", "events": "api.events"},
    "sharedKernel": "sharedkernel",
    "compositionRoot": "infrastructure",
}

TC, LI, AT, RF, NA = "type-checker", "linter", "ast-test", "reformulated", "n/a"
IMP, S, R, M, F = "imports", "source", "runtime", "mypy", "ruff"

META_CHK = (
    "No decorator, no base and no field default (Field(...), Column(...)) comes from a configured framework "
    "(django, fastapi, flask, litestar, marshmallow, pydantic, sqlalchemy, sqlmodel, starlette by default)."
)


def m(
    category: str,
    enforcement: list[str],
    selects: str = "",
    checks: str = "",
    title: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    return dict(category=category, enforcement=enforcement, selects=selects, checks=checks, title=title, reason=reason)


MAPPING = {
    # --- layered -----------------------------------------------------------------------------------------------
    "DCA-LAY-001": m(
        AT,
        [],
        "Informational - selects nothing.",
        "Informational - carries doctrine only. The dependency direction is held by the import rules.",
    ),
    "DCA-LAY-002": m(
        AT,
        [IMP],
        "Every module in a domain package, the shared kernel's included.",
        "It imports no module of a context's infrastructure package nor of the composition root.",
    ),
    "DCA-LAY-003": m(
        AT,
        [IMP],
        "Every module in an application package.",
        "It imports no module of a context's infrastructure package or of the composition root, and no "
        "module of a configured framework; it reaches them through its output ports.",
    ),
    "DCA-LAY-004": m(
        RF,
        [S],
        "Modules in a domain package or an incoming adapter.",
        "None names the building block TransactionBoundary or declares a transaction with a framework "
        "decorator (transaction.atomic, ...). Python has no declarative transaction on a use case in "
        "DCA's reading: the boundary is the explicit port, held by the application.",
    ),
    "DCA-LAY-005": m(
        NA,
        [],
        reason="dca_building_blocks is a regular package installed as a distribution; a project "
        "cannot add a module to it, so its port module holds what the library declares and nothing else.",
    ),
    "DCA-LAY-007": m(
        AT,
        [S],
        "Every module below the base package.",
        "Informational - lists every module that sits in no layer (outside domain, application, adapter, "
        "infrastructure, api of a context, the shared kernel and the composition root), and never fails.",
    ),
    # --- onion -------------------------------------------------------------------------------------------------
    "DCA-ONI-001": m(AT, [IMP], "Every module in a domain package.", "It imports no module of an application package."),
    "DCA-ONI-002": m(
        AT,
        [IMP, F],
        "Every module in a domain package, the shared kernel's included.",
        "It imports the standard library, the building blocks, the project's own modules and the "
        "configured allowed-in-domain libraries only. A per-directory ruff.toml with banned-api holds the "
        "same while editing.",
    ),
    "DCA-ONI-003": m(
        AT,
        [S],
        "Classes in a domain package.",
        META_CHK,
        title="Domain models must not carry prohibited framework decorators, bases or field metadata",
    ),
    # --- hexagonal ---------------------------------------------------------------------------------------------
    "DCA-HEX-001": m(AT, [IMP], "Every module in a domain package.", "It imports no module of an adapter package."),
    "DCA-HEX-002": m(
        AT, [IMP], "Every module in an application package.", "It imports no module of an adapter package."
    ),
    "DCA-HEX-003": m(
        AT,
        [S],
        "Modules in an incoming adapter package.",
        "None names a class that carries the Repository role, protocol or implementation.",
    ),
    "DCA-HEX-004": m(
        AT,
        [IMP],
        "Modules in an incoming adapter package.",
        "None imports a module of a context's infrastructure package or of the composition root.",
    ),
    "DCA-HEX-005": m(
        AT,
        [IMP],
        "Modules in an outgoing adapter package.",
        "None imports the infrastructure package of another context.",
    ),
    "DCA-HEX-006": m(
        AT,
        [IMP],
        "Modules in an incoming adapter package, the event consumers excluded.",
        "None imports a module of the outgoing adapters of the same context.",
    ),
    "DCA-HEX-007": m(
        AT,
        [IMP],
        "Modules in an incoming adapter package.",
        "None imports a module of another context; an event consumer may import that context's api.events.",
    ),
    "DCA-HEX-008": m(
        AT,
        [S],
        "Classes, protocols excluded, whose name ends with Repository.",
        "Each sits in an outgoing adapter package.",
    ),
    "DCA-HEX-009": m(
        AT,
        [S],
        "Protocol classes in an application's shared package.",
        "Each carries the OutputPort role, through OutputPort, Repository, Store or a publisher.",
    ),
    "DCA-HEX-010": m(AT, [S], "Protocol classes that carry the OutputPort role.", "None sits in a domain package."),
    "DCA-HEX-011": m(
        AT,
        [S],
        "Modules in an incoming adapter package.",
        "None names a use case - a class, no protocol, that carries the InputPort role; naming the input "
        "port protocol is what the rule expects.",
    ),
    "DCA-HEX-012": m(
        AT, [S], "Modules in an incoming adapter package.", "None names a class that carries the DomainService role."
    ),
    "DCA-HEX-013": m(
        AT,
        [S],
        "Modules in an outgoing adapter package.",
        "None names a class or protocol that carries the InputPort role.",
    ),
    "DCA-HEX-014": m(
        RF,
        [S],
        'Handler functions a router decorator registers for GET: <router>.get("/path") or '
        "route/api_route with methods containing GET (FastAPI, Flask, Litestar style).",
        "No such function constructs a class whose name ends with Command.",
    ),
    "DCA-HEX-016": m(
        RF,
        [S],
        "Modules in an adapter package.",
        "Informational - lists every <Enum>.<MEMBER>.name of an enum declared in a domain or application "
        "package, and never fails. A member read through a variable is not seen.",
    ),
    "DCA-HEX-017": m(
        RF,
        [S],
        "Functions registered as event listener by the configured listener decorators.",
        "A listener that calls an input port runs after the commit in its own transaction, as the preset "
        "expresses it. Python has no common listener decorator; without a preset nothing is selected.",
    ),
    "DCA-HEX-018": m(
        RF,
        [S],
        'Functions a router decorator registers (<router>.<method>("/path", ...)), anywhere below the base package.',
        "Each sits in an incoming adapter package. Python handlers are functions, not classes.",
    ),
    "DCA-HEX-019": m(
        AT,
        [S],
        "Classes, protocols excluded, that carry the OutputPort role but neither Repository nor Store.",
        "Each sits in an outgoing adapter package; in the composition root only a bridge that drives an input port.",
    ),
    "DCA-HEX-020": m(
        RF,
        [S],
        "Modules in an incoming adapter package. Nothing is selected when the configured "
        "authorization forms ([tool.dca] authorization-decorators) are empty.",
        "Informational - lists every call of a method that asks whether the caller holds a role or a "
        "permission - has_role, has_any_role, has_authority, has_any_authority, is_in_role, "
        "is_user_in_role, has_perm, has_perms - on any owner, and never fails. The declared forms are "
        "a decorator (Django's permission_required, Flask-Login's login_required) or a parameter default "
        "(FastAPI's Security); a role compared by the adapter itself or a helper of the project's own is "
        "not seen.",
    ),
    # --- tactical ----------------------------------------------------------------------------------------------
    "DCA-TAC-001": m(
        AT,
        [S],
        "Classes in a domain package whose name ends with AggregateRoot.",
        "The class carries the AggregateRoot role.",
    ),
    "DCA-TAC-002": m(
        AT,
        [S],
        "Classes that carry the AggregateRoot role.",
        "No field annotation, generic arguments included, names a class with the OutputPort role or a "
        "port building block.",
    ),
    "DCA-TAC-003": m(
        AT,
        [S],
        "Classes that carry the AggregateRoot role.",
        "No field annotation, through generic arguments, names another class with the AggregateRoot role. "
        "Fields are class-level annotations and the self.<name> assignments of __init__, typed by "
        "their annotation or by the parameter assigned.",
    ),
    "DCA-TAC-004": m(
        AT,
        [M, S],
        "Classes, protocols excluded and the most derived only, that carry the Entity role.",
        "Entity declares id as an abstract property, so an entity without it cannot be built and the "
        "type checker refuses it; the source test checks that a field, its own or a base's, holds a "
        "class with the Id role, so the identity is state, not computed.",
    ),
    "DCA-TAC-005": m(
        RF,
        [S],
        "Every call of a class that carries the Entity role but not AggregateRoot.",
        "It happens in a domain module of the entity's own context. Python has no package-private "
        "constructor; the call site is what the rule reads.",
    ),
    "DCA-TAC-006": m(
        AT,
        [S],
        "Classes that carry the Entity or Value role.",
        "No method named set_<name> takes exactly one parameter, and no property has a setter.",
    ),
    "DCA-TAC-007": m(
        AT,
        [S],
        "Classes that carry the Entity role but not AggregateRoot.",
        "No field annotation, through generic arguments, names a class with the AggregateRoot role.",
    ),
    "DCA-TAC-008": m(
        AT,
        [S],
        "Classes that carry the Value role.",
        "No field annotation, through generic arguments, names a class with the Entity role.",
    ),
    "DCA-TAC-009": m(
        RF,
        [S],
        "Every class of the project.",
        "None names a concrete value - a class with the Value role that declares fields - among its "
        "bases. Python has no final class at runtime; typing.final is the type checker's view of the "
        "same.",
        title="Value Objects must not be extended",
    ),
    "DCA-TAC-010": m(
        RF,
        [R, S],
        "Classes that carry the Value role.",
        "The base makes every value a frozen dataclass, so an assignment to a field raises. The source "
        "test refuses a field typed as a mutable collection (list, dict, set, ...) and a method other "
        "than __init__/__post_init__ that assigns to self or calls object.__setattr__.",
        title="Value Objects must not mutate their state",
    ),
    "DCA-TAC-011": m(AT, [S], "Classes that carry the Value role.", "No method is named set_<name>."),
    "DCA-TAC-012": m(
        RF,
        [R, S],
        "Classes that carry the Value role.",
        "The base makes every value a dataclass with attribute equality. The source test refuses an "
        "__eq__ of its own and a dataclass decorator with eq=False.",
    ),
    "DCA-TAC-013": m(
        AT,
        [S],
        "Classes in an application package whose name ends with Repository.",
        "The class carries the Repository role.",
    ),
    "DCA-TAC-014": m(
        AT,
        [S],
        "Protocol classes that carry the Repository role.",
        "Each sits in an application package, the shared kernel's included.",
    ),
    "DCA-TAC-015": m(
        AT,
        [S],
        "Classes, protocols excluded, that carry the Repository role.",
        "Each sits in an outgoing adapter package. A role is nominal: an implementation names its port "
        "among its bases (DCA-PY-003).",
    ),
    "DCA-TAC-016": m(
        TC,
        [M, S],
        "Protocol classes that carry the Repository role through Repository[A, K].",
        "The bound A: AggregateRoot makes a repository for anything else a type error. The source test "
        "checks the first type argument: a class with the AggregateRoot role, and the port named after "
        "it plus Repository.",
    ),
    "DCA-TAC-017": m(
        AT,
        [S],
        "Protocol classes that carry the Repository role.",
        "No method's return annotation names a class with the Entity role but not AggregateRoot.",
    ),
    "DCA-TAC-018": m(
        AT,
        [S],
        "Protocol classes outside adapter and infrastructure packages whose name ends with Store.",
        "The class carries the Store role and not the Repository role.",
    ),
    "DCA-TAC-019": m(AT, [S], "Protocol classes that carry the Store role.", "Each sits in an application package."),
    "DCA-TAC-020": m(
        AT, [S], "Classes, protocols excluded, that carry the Store role.", "Each sits in an outgoing adapter package."
    ),
    "DCA-TAC-021": m(
        AT,
        [S],
        "Protocol classes that carry the Store role.",
        "No method declared on the protocol itself is named save, delete or delete_by_id.",
    ),
    "DCA-TAC-023": m(
        RF,
        [S],
        "Every call of a class that carries the AggregateRoot role.",
        "It happens in the module that declares the root - its class methods (create, restore, ...) "
        "build it and check its invariants. Python has no private constructor; the call site is what "
        "the rule reads.",
        title="Aggregate Roots are built through their own class methods",
    ),
    "DCA-TAC-024": m(
        AT,
        [S],
        "Class methods of classes that carry the Value role.",
        "No neutral factory (of, new, create, value_of, make) takes the same parameter types, in the same "
        "order, as another class method. Two named origins (from_input, from_stored) pass.",
    ),
    "DCA-TAC-025": m(
        AT,
        [S],
        "Classes in a domain package, the shared kernel's included. Not selected: a value or "
        "id whose one field is value, exceptions, enums.",
        "No field, parameter of a public method or return annotation names str, int, float, bytes, "
        "complex, a datetime type, timedelta or uuid.UUID. A private bool field - a single yes/no fact - "
        "and a bool return - a predicate - pass; a bool parameter and a public bool field do not.",
    ),
    "DCA-TAC-026": m(
        AT,
        [S],
        "The repository protocols that bind a class with both the Owned and the AggregateRoot "
        "role as the first type argument of Repository[A, K] (or of a narrower port).",
        "The owner id type is the type argument of Owned[...] among the aggregate's bases; a bare Owned "
        "is reported. At least one method of the repository, inherited protocol methods included, takes "
        "a parameter annotated with the aggregate's id type (K, or else the return of its id property) "
        "and one annotated with the owner id type, in either position, and returns an annotation that "
        "names the aggregate (itself, Optional, a list ...). A method answering bool does not count. "
        "Whether a use case calls the scoped lookup is not checked.",
    ),
    # --- strategic ---------------------------------------------------------------------------------------------
    "DCA-STR-001": m(
        AT,
        [S],
        "Every context package and the shared kernel.",
        "Informational - lists each context with its declared name and module count, and never fails.",
    ),
    "DCA-STR-002": m(AT, [IMP], "Every module of the shared kernel.", "It imports no module of a context."),
    "DCA-STR-003": m(
        AT,
        [IMP],
        "Every module in a context's application package.",
        "It imports no module of another context, that context's api included; another context is "
        "reached through an output port.",
    ),
    "DCA-STR-004": m(
        AT,
        [IMP],
        "Every module in a context's domain package.",
        "It imports no module of another context, that context's api included.",
    ),
    "DCA-STR-005": m(
        AT,
        [S],
        "Classes that carry the OpenHostService role.",
        "Each sits in an api package or in an incoming adapter package.",
    ),
    "DCA-STR-006": m(
        AT,
        [IMP],
        "Every module in a context's adapter packages.",
        "An import of another context names that context's api (or api.events) only.",
    ),
    "DCA-STR-007": m(AT, [S], "Classes that carry the IntegrationEvent role.", "Each sits in an api.events package."),
    "DCA-STR-008": m(
        RF,
        [R, S],
        "Classes that carry the IntegrationEvent role.",
        "The base makes every integration event a frozen dataclass; the source test refuses a mutable "
        "collection field and a method that assigns to self.",
    ),
    "DCA-STR-010": m(
        AT,
        [],
        "Informational - selects nothing.",
        "Nothing is asserted. Whether a consumed integration event is translated before it reaches the "
        "domain is a review check.",
    ),
    "DCA-STR-011": m(
        AT,
        [S],
        "The packages directly below the base package.",
        "At least one declares __dca__ = BoundedContext(...) in its __init__.py.",
    ),
    "DCA-STR-012": m(AT, [S], "Every module below the base package.", "At least one sits in a DCA layer."),
    "DCA-STR-013": m(
        AT, [S], "Classes in an api.events package, enums excluded.", "Each carries the IntegrationEvent role."
    ),
    # --- context map -------------------------------------------------------------------------------------------
    "DCA-MAP-001": m(
        RF,
        [S],
        "Every call of the building blocks Upstream, ExternalUpstream and Partnership.",
        "It sits in the __init__.py of a package that declares a bounded context.",
    ),
    "DCA-MAP-002": m(
        RF,
        [S],
        "Every ExternalUpstream of a context's declaration.",
        "name is not blank and not a context's name, and (name, interaction) occurs once per context.",
    ),
    "DCA-MAP-004": m(
        RF,
        [S],
        "Every Upstream of a context's declaration.",
        "context names a declared context and not the declaring one.",
    ),
    "DCA-MAP-005": m(
        RF,
        [S],
        "Every Upstream of a context's declaration.",
        "via holds at least one channel, and (context, channel) occurs once per context.",
    ),
    "DCA-MAP-006": m(
        NA,
        [],
        reason="Python has no second module declaration (no Spring Modulith allowedDependencies, "
        "no Cargo.toml per context): __dca__ is the only one, and DCA-MAP-007/011 compare it with the "
        "imports.",
    ),
    "DCA-MAP-007": m(
        RF,
        [S, IMP],
        "Every implemented Upstream of a context's declaration.",
        "For each channel, a module of the declaring context imports the target's api (api channel) or "
        "api.events (events channel).",
    ),
    "DCA-MAP-008": m(
        RF,
        [IMP],
        "Imports into another context's api by a context that declares it with Translation.ANTI_CORRUPTION_LAYER.",
        "The api channel is imported only by the outgoing adapters, the events channel only by the incoming adapters.",
    ),
    "DCA-MAP-009": m(
        RF,
        [IMP],
        "Imports into another context's api by a context that declares it with Translation.CONFORMIST.",
        "None comes from a domain module.",
    ),
    "DCA-MAP-010": m(
        RF,
        [IMP],
        "Imports of the contract_packages an ExternalUpstream names.",
        "With an anti-corruption layer only the matching adapter imports them (outgoing for OUTBOUND, "
        "incoming for INBOUND); with conformist, no domain module does.",
    ),
    "DCA-MAP-011": m(
        RF,
        [IMP],
        "Every import of a context's module into another context's api or api.events.",
        "The importing context declares an Upstream for that context with that channel in via.",
    ),
    "DCA-MAP-012": m(
        RF,
        [S],
        "Every Partnership of a context's declaration.",
        "It names a declared context other than itself, and that context declares the partnership back.",
    ),
    "DCA-MAP-013": m(
        AT,
        [S],
        "Every Upstream, ExternalUpstream and Partnership.",
        "Informational - lists every declared edge and never fails.",
    ),
    "DCA-MAP-014": m(
        NA,
        [],
        reason="Python has no module declaration with allowed dependencies besides __dca__; "
        "DCA-MAP-007 already requires every declared edge to be backed by an import.",
    ),
    # --- advanced ----------------------------------------------------------------------------------------------
    "DCA-ADV-001": m(
        RF,
        [R, S],
        "Classes in a domain package whose name ends with Event, and classes that carry the DomainEvent role.",
        "A class named an event carries the DomainEvent role; an event is a frozen "
        "dataclass by its base, holds no mutable collection and no method assigns to self.",
    ),
    "DCA-ADV-002": m(AT, [S], "Classes that carry the DomainEvent role.", "Each sits in a domain package."),
    "DCA-ADV-004": m(AT, [S], "Classes in a domain package that carry the DomainEvent role.", META_CHK),
    "DCA-ADV-005": m(
        RF,
        [R, S],
        "The most derived classes that carry the IntegrationEvent role.",
        "The class statement passes event_type (and version) as class keywords; the base refuses a class "
        "without it when the module is imported. Python has no annotations on a class; the keywords are "
        "the metadata.",
        title="Integration Events must name their event type",
    ),
    "DCA-ADV-006": m(
        AT,
        [S],
        "Classes that carry the IntegrationEvent role.",
        "No field is named schema_version, event_version or contract_version.",
    ),
    "DCA-ADV-007": m(
        AT,
        [S],
        "Classes that carry the DomainEvent role but not IntegrationEvent.",
        "No field is named schema_version, event_version or contract_version.",
    ),
    "DCA-ADV-008": m(
        AT,
        [S],
        "The most derived classes that carry the DomainEvent role.",
        "A field, its own or a base's, is of one of the configured timestamp types (by default the "
        "building blocks' Timestamp, or datetime).",
    ),
    "DCA-ADV-010": m(AT, [S], "Classes that carry the DomainService role.", "Each sits in a domain package."),
    "DCA-ADV-011": m(AT, [S], "Classes in a domain package that carry the DomainService role.", META_CHK),
    "DCA-ADV-012": m(
        RF,
        [S],
        "Classes that carry the DomainService role.",
        "No method other than __init__ assigns to self. Python has no final field; statelessness is the "
        "absence of mutation.",
    ),
    "DCA-ADV-013": m(AT, [S], "Classes that carry the Factory role.", "The name ends with Factory."),
    "DCA-ADV-014": m(AT, [S], "Classes that carry the Factory role.", "Each sits in a domain package."),
    "DCA-ADV-015": m(AT, [S], "Classes in a domain package that carry the Factory role.", META_CHK),
    "DCA-ADV-016": m(RF, [S], "Classes that carry the Factory role.", "No method other than __init__ assigns to self."),
    "DCA-ADV-017": m(
        AT,
        [S],
        "Classes that carry the Specification role or whose name ends with Specification.",
        "Each sits in a domain package.",
    ),
    "DCA-ADV-018": m(AT, [S], "Specifications in a domain package.", META_CHK),
    "DCA-ADV-019": m(
        AT,
        [S],
        "Methods of classes that carry the Entity or Value role.",
        "No method calls a class with the DomainService role or a function on it. A parameter of that "
        "type alone is not reported.",
    ),
    "DCA-ADV-020": m(
        AT,
        [S],
        "Public methods of classes that carry the DomainService role.",
        "At least one parameter's annotation names a class with the Entity role.",
    ),
    # --- use case ----------------------------------------------------------------------------------------------
    "DCA-USE-001": m(AT, [S], "Classes named InputPort below the base package.", "There is none."),
    "DCA-USE-002": m(AT, [S], "Classes whose name ends with Command.", "Each sits in an application package."),
    "DCA-USE-003": m(AT, [S], "Classes whose name ends with Query.", "Each sits in an application package."),
    "DCA-USE-004": m(
        RF,
        [S],
        "Classes in an application package whose name ends with Command.",
        "Each is a frozen dataclass, a NamedTuple or an enum, and holds no mutable collection.",
    ),
    "DCA-USE-005": m(
        RF,
        [S],
        "Classes in an application package whose name ends with Query.",
        "Each is a frozen dataclass, a NamedTuple or an enum, and holds no mutable collection.",
    ),
    "DCA-USE-006": m(
        AT,
        [S],
        "Classes whose name ends with Result and that do not carry the Value role.",
        "Each sits in an application package.",
    ),
    "DCA-USE-007": m(
        RF,
        [S],
        "Classes in an application package whose name ends with Result.",
        "Each is a frozen dataclass, a NamedTuple or an enum, and holds no mutable collection. A case of a "
        "closed result need not be named ...Result; the union alias is.",
    ),
    "DCA-USE-008": m(AT, [S], "Classes whose name ends with Response.", "Each sits in an adapter package."),
    "DCA-USE-009": m(
        RF,
        [S],
        "Use cases: classes, protocols excluded, that carry the InputPort role.",
        "A use case that calls save on an attribute typed with a Repository also calls publish or "
        "publish_and_clear_events on an attribute typed with a DomainEventPublisher. An attribute's type "
        "is its annotation or that of the __init__ parameter assigned to it.",
    ),
    "DCA-USE-010": m(
        AT, [S], "Modules in a domain package.", "None declares or names a class whose name ends with Dto."
    ),
    "DCA-USE-011": m(
        AT, [S], "Modules in an application package.", "None declares or names a class whose name ends with Dto."
    ),
    "DCA-USE-012": m(
        RF,
        [S],
        "Use cases.",
        "Every call of save, delete or delete_by_id on a Repository and of publish... on a "
        "DomainEventPublisher sits inside the work the use case hands to "
        "TransactionBoundary.in_transaction or in_transaction_closed - a lambda, a nested function or a "
        "method of its own. The explicit boundary is the only form.",
    ),
    "DCA-USE-013": m(
        NA,
        [],
        reason="DCA's Python transaction boundary is the explicit TransactionBoundary port, which "
        "DCA-USE-012 reads; the rule selects only declaratively transactional use cases.",
    ),
    "DCA-USE-014": m(
        AT,
        [S],
        "Use cases in an application package, the shared package excluded.",
        "All of a context sit at one depth: application.<use_case> or application.<feature>.<use_case>.",
    ),
    "DCA-USE-015": m(
        AT,
        [S],
        "Classes in an application package whose name ends with Result.",
        "No field annotation, through generic arguments and into other application classes, names a class "
        "with the Entity role.",
    ),
    "DCA-USE-016": m(AT, [S], "Use cases.", "No field names a class or protocol with the InputPort role."),
    "DCA-USE-017": m(AT, [S], "Use cases.", "No public method other than execute."),
    "DCA-USE-018": m(
        AT,
        [S],
        "Modules of an incoming adapter of a context whose use cases are grouped by feature.",
        "The commands a module constructs belong to one feature.",
    ),
    "DCA-USE-019": m(
        AT,
        [S],
        "Use cases whose execute takes a class whose name ends with Query.",
        "No call of a write (save, delete, remove, add, insert, update, append, put, store) on a Repository "
        "or Store attribute, and no publish on a publisher.",
    ),
    "DCA-USE-020": m(
        AT,
        [S, F],
        "Use cases.",
        "No call of uuid.UUID(...). Parsing happens in the adapter or in the "
        "id's own constructor; a per-directory ruff.toml (banned-api uuid.UUID) holds it while editing.",
    ),
    # --- naming ------------------------------------------------------------------------------------------------
    "DCA-NAM-001": m(AT, [S], "Use cases in an application package.", "The name ends with UseCase."),
    "DCA-NAM-002": m(
        NA,
        [],
        reason="Python has no injectable stereotype decorator in DCA's reading: the composition "
        "root constructs use cases in code, so there is nothing to list.",
    ),
    "DCA-NAM-003": m(
        AT,
        [S],
        "Protocol classes in an application package that carry the InputPort role.",
        "The name ends with InputPort.",
    ),
    "DCA-NAM-004": m(
        AT, [S], "Classes in an application package whose name contains Repository.", "The name ends with Repository."
    ),
    "DCA-NAM-005": m(
        NA,
        [],
        reason="Python web handlers are functions registered by a router decorator, not "
        "controller classes; the module that holds them carries the name, and DCA-HEX-018 places it.",
    ),
    "DCA-NAM-006": m(
        NA,
        [],
        reason="Python web handlers are functions registered by a router decorator, not "
        "resource classes; the module that holds them carries the name, and DCA-HEX-018 places it.",
    ),
    "DCA-NAM-007": m(AT, [S], "Classes whose name ends with Dto.", "Each sits in an adapter package."),
    "DCA-NAM-008": m(AT, [S], "Classes whose name ends with Converter.", "Each sits in an adapter package."),
    "DCA-NAM-009": m(
        AT,
        [S],
        "Every module and package of a context and of the shared kernel.",
        "None is named entities, entity, value_objects, valueobjects, helpers, helper, util or utils.",
    ),
    "DCA-NAM-010": m(
        AT, [S], "Classes in a domain package.", "No name ends with Helper, Util, Utils, Impl or Implementation."
    ),
    "DCA-NAM-011": m(
        AT, [S], "Classes whose name ends with ViewModel.", "Each sits in the incoming adapters' web package."
    ),
    "DCA-NAM-012": m(
        AT,
        [S],
        "Input ports and use cases in an application package.",
        "Informational - lists names that start with On, After, When, Upon or Before followed by a "
        "capital, and never fails.",
    ),
    "DCA-NAM-013": m(
        AT,
        [S],
        "Input ports and use cases in an application package, and public functions of an api package.",
        "No class name starts with Set or Update followed by a capital, and no function "
        "name starts with set_ or update_.",
    ),
    # --- cycles ------------------------------------------------------------------------------------------------
    "DCA-CYC-001": m(
        AT, [IMP], "One slice per context: its domain package.", "The slices import each other in no cycle."
    ),
    "DCA-CYC-002": m(
        AT, [IMP], "One slice per context: its application package.", "The slices import each other in no cycle."
    ),
    "DCA-CYC-003": m(
        AT, [IMP], "One slice per context: its outgoing adapter package.", "The slices import each other in no cycle."
    ),
    "DCA-CYC-004": m(
        AT, [IMP], "One slice per context: its incoming adapter package.", "The slices import each other in no cycle."
    ),
    "DCA-CYC-005": m(
        AT,
        [IMP],
        "One slice per use-case or feature module or package of a context's application, the shared package excluded.",
        "The slices import each other in no cycle.",
    ),
    # --- errors ------------------------------------------------------------------------------------------------
    "DCA-ERR-001": m(AT, [S], "Exception classes in a domain package.", "Each carries the DomainException role."),
    "DCA-ERR-002": m(
        AT,
        [S],
        "Classes that carry the DomainException or the PortException role.",
        "A DomainException sits in a domain package, a port exception in an application package - an "
        "output port's exception beside the port, although the adapter raises it.",
    ),
    "DCA-ERR-003": m(
        AT,
        [S],
        "Exception classes in an application package that do not carry DomainException.",
        "Each carries UseCaseException or OutputPortException; extending only PortException or "
        "InputPortException does not count.",
    ),
    "DCA-ERR-004": m(
        AT,
        [S],
        "Classes that carry DomainException or PortException.",
        "No base and no decorator comes from a configured framework - an HTTPException base included.",
    ),
    "DCA-ERR-005": m(
        AT,
        [S],
        "Classes that carry DomainException or PortException.",
        "The name contains none of Http, HTTP, StatusCode, ResponseStatus, Response.",
    ),
    "DCA-ERR-006": m(
        AT,
        [S],
        "Modules of an incoming adapter that name an input port.",
        "Informational - lists a module that names no class with the DomainException or UseCaseException "
        "role and no case of a closed result, and never fails. A closed result is the union an input "
        "port answers with: the second type argument of UseCase[IMP, O] or execute's return annotation, "
        "through a type alias. Whether a match covers every case is the type checker's "
        "(assert_never; DCA-PY-006). It also lists a module that names PortException, "
        "InputPortException or OutputPortException itself. Nothing is listed when the project has "
        "neither a failure class nor a closed result.",
    ),
    "DCA-ERR-007": m(
        AT,
        [S],
        "Classes that carry DomainException or PortException, and their fields.",
        "Informational - lists every field annotated str or with an entity, and never fails.",
    ),
    "DCA-ERR-008": m(
        AT,
        [S],
        "Closed results, as DCA-ERR-006 finds them; a case that is an exception is not one.",
        "Informational - lists every closed result none of whose cases carries the Refusal role, and "
        "never fails. A result whose outcomes are all successes is correct as it is.",
    ),
    "DCA-ERR-009": m(
        AT,
        [S],
        "Every call of a class with the DomainException role in a module outside the domain packages.",
        "There is none - only the domain constructs a domain exception. Re-raising one the "
        "application caught is no construction.",
    ),
}

PYTHON_ONLY = [
    dict(
        id="DCA-PY-001",
        title="A domain dataclass is frozen, by its base where it is a value, an id or an event",
        rationale="A @dataclass without frozen=True in the domain is a mutable record without identity: neither a "
        "value nor an entity. A Value, Id or DomainEvent is a frozen dataclass by its base; a decorator of "
        "its own fails at import or quietly changes what the base set.",
        category=AT,
        enforcement=[S],
        selects="Classes in a domain package with a dataclass decorator.",
        checks="A class with the Value, DomainEvent or IntegrationEvent role carries none; any other class that is "
        "no entity carries frozen=True.",
    ),
    dict(
        id="DCA-PY-002",
        title="Entities compare by identity",
        rationale="A dataclass compares every field, which is value equality. Two states of the same entity must be "
        "equal and two entities with equal data must not; Entity gives identity equality, a dataclass "
        "decorator or an __eq__ of its own replaces it.",
        category=AT,
        enforcement=[S],
        selects="Classes that carry the Entity role, aggregate roots included.",
        checks="No dataclass decorator unless it says eq=False, and no __eq__ of its own.",
    ),
    dict(
        id="DCA-PY-003",
        title="An output port is implemented by name",
        rationale="A Protocol is structural: an adapter fits a port without naming it, and the rules - which read "
        "roles from bases - lose the implementation, and with it the placement rules. A port nobody names "
        "is a port the rules cannot follow to its adapter.",
        category=AT,
        enforcement=[S],
        selects="Protocol classes that carry the OutputPort role, and the classes of "
        "the outgoing adapters and the composition root.",
        checks="Every port is named among the bases of some class or of a narrower port; no class of the outgoing "
        "adapters or the composition root fits a port's methods, by name and parameter names, without naming it - "
        "nor the methods of a building block's port (Repository, DomainEventPublisher, TransactionBoundary).",
    ),
    dict(
        id="DCA-PY-004",
        title="The domain stays synchronous",
        rationale="Async is an I/O concern of ports and adapters. A synchronous domain stays testable and "
        "deterministic and pulls no event loop into the model; the use case awaits its ports and calls the "
        "domain plainly.",
        category=AT,
        enforcement=[S],
        selects="Every module in a domain package.",
        checks="No async def and no import of asyncio, trio or anyio.",
    ),
    dict(
        id="DCA-PY-005",
        title="The domain reads no clock and no randomness",
        rationale="A domain that reads the time or draws a random value gives different results for the same input, "
        "so its tests depend on the moment they run. The value comes in from the application as a "
        "parameter.",
        category=AT,
        enforcement=[S, F],
        selects="Every module in a domain package.",
        checks="No call of datetime.now/utcnow/today, date.today, time.time/monotonic/perf_counter, uuid.uuid1/4/7, "
        "os.urandom, secrets.* or random.*. A per-directory ruff.toml with banned-api holds the same while "
        "editing.",
    ),
    dict(
        id="DCA-PY-006",
        title="A match over a closed result does not swallow a case it does not know",
        rationale="Python's exhaustiveness over a union is the type checker's, and only where the match ends in "
        "assert_never: a wildcard case that answers something swallows the case a use case adds tomorrow, "
        "which Java's sealed switch and Rust's match would refuse.",
        category=TC,
        enforcement=[M, S],
        selects="match statements with a class pattern naming a case of a closed result (DCA-ERR-006).",
        checks="A wildcard case (case _:) calls assert_never; the type checker then refuses a match that misses a "
        "case.",
    ),
    dict(
        id="DCA-PY-007",
        title="Cancellation passes through",
        rationale="asyncio.CancelledError is a BaseException so that cancellation reaches the task that awaits. A "
        "handler that catches it - by name, as BaseException or bare - and does not raise again turns a "
        "cancelled request into one that goes on.",
        category=AT,
        enforcement=[S],
        selects="except clauses in every module that sits in a layer.",
        checks="A bare except, an except BaseException and an except CancelledError raises again.",
    ),
]


def implemented_ids() -> set[str]:
    try:
        from dca_rules.rules import implemented
    except ImportError:
        return set()
    return set(implemented())


def main() -> None:
    java_path, out_path = sys.argv[1], sys.argv[2]
    with open(java_path, encoding="utf-8") as handle:
        java = json.load(handle)
    implemented = implemented_ids()
    rules: list[dict[str, object]] = []
    missing = []
    for r in java["rules"]:
        mapping = MAPPING.get(r["id"])
        if mapping is None:
            missing.append(r["id"])
            continue
        if mapping["category"] == NA:
            rules.append(dict(set=r["set"], id=r["id"], status="n/a", reason=mapping["reason"]))
            continue
        rules.append(
            dict(
                set=r["set"],
                id=r["id"],
                title=mapping["title"] or r["title"],
                rationale=r["rationale"],
                selects=mapping["selects"],
                checks=mapping["checks"],
                implementation="python",
                status=r.get("status", "enforced"),
                maturity=r.get("maturity", "released"),
                category=mapping["category"],
                enforcement=mapping["enforcement"],
                implemented=r["id"] in implemented,
            )
        )
    extra = sorted(set(MAPPING) - {r["id"] for r in java["rules"]})
    if missing or extra:
        sys.exit(f"mapping out of step with the Java catalogue: missing {missing}, unknown {extra}")
    for py in PYTHON_ONLY:
        rules.append(
            dict(
                set="python",
                id=py["id"],
                title=py["title"],
                rationale=py["rationale"],
                selects=py["selects"],
                checks=py["checks"],
                implementation="python",
                status="enforced",
                maturity="experimental",
                category=py["category"],
                enforcement=py["enforcement"],
                implemented=py["id"] in implemented,
            )
        )
    unknown = sorted(implemented - {str(r["id"]) for r in rules})
    if unknown:
        sys.exit(f"the suite implements ids the catalogue lacks: {unknown}")
    out = dict(library="dca-python", version="0.0.0", layout=LAYOUT, retired=java.get("retired", []), rules=rules)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
