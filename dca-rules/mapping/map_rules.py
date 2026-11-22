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
# adapter.incoming[.event|.web], adapter.outgoing, infrastructure, api, events}, <base>.sharedkernel (the same layers,
# no api and no events),
# <base>.infrastructure (the composition root). A role is a building block named among a class's bases, transitively.
# An interface is Java's interface: a typing.Protocol class, or an abc.ABC (or abc.ABCMeta class) whose methods are all
# abstract and that holds no field. Every class is read, a nested one as a class of its own. A class's fields are its
# class-level annotations and the self.<name> assignments of every method, typed by their annotation, the parameter
# assigned or the class a call constructs; a rule over a class reads the fields and methods of its bases that carry no
# role as its own.
LAYOUT = {
    "declaration": "[tool.dca] in pyproject.toml; a context: __dca__ = BoundedContext(...) in its __init__.py",
    "layers": ["domain", "application", "adapter.incoming", "adapter.outgoing", "infrastructure", "api", "events"],
    "applicationShared": "shared",
    "adapterModules": {"incoming": "adapter.incoming", "outgoing": "adapter.outgoing", "event": "event", "web": "web"},
    "publishedPackages": {"api": "api", "events": "events"},
    "sharedKernel": "sharedkernel",
    "compositionRoot": "infrastructure",
    # Every package name above is renamed in [tool.dca] under its own key (incoming, outgoing, shared, event, web,
    # api, events, shared-kernel, infrastructure, domain, application, adapter), as are the suffixes and the operation
    # containers (Java's DcaLayout with...Subpackage, with...Suffix, withOperationContainers); a rule's text names
    # the default.
    "configurable": {
        "operationContainers": [],
        "suffixes": {
            "use-case-suffix": "UseCase",
            "input-port-suffix": "InputPort",
            "aggregate-root-suffix": "AggregateRoot",
            "repository-suffix": "Repository",
            "store-suffix": "Store",
            "factory-suffix": "Factory",
            "specification-suffix": "Specification",
        },
    },
}

TC, LI, AT, RF, NA = "type-checker", "linter", "ast-test", "reformulated", "n/a"
IMP, S, R, M, F = "imports", "source", "runtime", "mypy", "ruff"

META_CHK = (
    "No decorator of the class or of one of its methods, no base, no default of a field or a class attribute "
    "(Field(...), Column(...)) or of a method parameter (Depends(...)), and no metadata of an Annotated[...] "
    "annotation of a field or a parameter comes from a configured framework (django, fastapi, flask, litestar, "
    "marshmallow, pydantic, sqlalchemy, sqlmodel, starlette by default)."
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
        "Every module in a layer. Read: transactional decorators (transaction-decorators: Django's atomic, "
        "transactional, Transactional by default, matched by qualified name or its last segments); a transaction run "
        "in code (transaction-apis: django.db.transaction.atomic called or entered, and .begin / .begin_nested entered "
        "in a with on any receiver, by default); and the building block TransactionBoundary (or "
        "AsyncTransactionBoundary) named - wiring - apart "
        "from the base of an implementation, which is never selected.",
        "Decorators and transactions run in code sit in an application package or an outgoing adapter; a domain, an "
        "incoming adapter, a context's infrastructure and the composition root are reported. TransactionBoundary is "
        "named in those two and in the composition root and the shared kernel's infrastructure as well; a domain, an "
        "incoming adapter and a context's infrastructure are reported.",
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
        "infrastructure, api, events of a context, the shared kernel and the composition root), and never fails.",
    ),
    "DCA-LAY-008": m(
        AT,
        [IMP],
        "Modules in an application package, the shared kernel's included; every import, function-level and "
        "TYPE_CHECKING imports too.",
        "None imports a module of a configured persistence or transaction library (persistence-apis: sqlite3, "
        "sqlalchemy, sqlmodel, psycopg, psycopg2, asyncpg, pymongo, motor, peewee, tortoise, django.db by default; "
        "a prefix covers its submodules). A session, a connection or a transaction opened in the use case needs "
        "the import and is reported with it; the application runs a transaction through TransactionBoundary. "
        "Python has no transactional decorator the rule would let pass, so none passes. An empty list checks "
        "nothing.",
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
    "DCA-ONI-004": m(
        AT,
        [S],
        "Modules in a domain package, the shared kernel's included. Exempt from the async part: the classes that "
        "carry the DomainGateway or the DomainService role, with their methods.",
        "Outside the exempt classes no function is async def, no expression awaits, no async for or async with, "
        "and no name resolves to a configured asynchronous type (async-types: typing's and collections.abc's "
        "Awaitable, Coroutine, AsyncIterator, AsyncIterable and AsyncGenerator by default); nowhere in the domain "
        "does an import name a configured asynchronous runtime (async-runtimes: asyncio, concurrent.futures, trio, "
        "anyio by default). This diverges from Java and .NET, whose domain is synchronous throughout, as Rust does: "
        "a domain gateway answers asynchronously when its adapter does, so the gateways and the domain services "
        "that await them may be async; aggregates, entities, values, events, failures, factories and "
        "specifications stay synchronous. The application and the adapters are not selected.",
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
        "None names a class that carries the Repository role, interface or implementation.",
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
        "None imports the infrastructure package of another context; its own context's and the shared kernel's "
        "infrastructure are shared support and pass.",
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
        "None imports a module of another context; an event consumer may import that context's events package.",
    ),
    "DCA-HEX-008": m(
        AT,
        [S],
        "Classes, interfaces excluded, whose name ends with Repository.",
        "Each sits in an outgoing adapter package.",
    ),
    "DCA-HEX-009": m(
        AT,
        [S],
        "Interfaces in an application's shared package.",
        "Each carries the OutputPort role, through OutputPort, Repository, Store or a publisher.",
    ),
    "DCA-HEX-010": m(AT, [S], "Interfaces that carry the OutputPort role.", "None sits in a domain package."),
    "DCA-HEX-011": m(
        AT,
        [S],
        "Modules in an incoming adapter package.",
        "None names a use case - a class, no interface, that carries the InputPort role; naming the input "
        "port interface is what the rule expects.",
    ),
    "DCA-HEX-012": m(
        AT, [S], "Modules in an incoming adapter package.", "None names a class that carries the DomainService role."
    ),
    "DCA-HEX-013": m(
        AT,
        [S],
        "Modules in an outgoing adapter package.",
        "None names a class or interface that carries the InputPort role.",
    ),
    "DCA-HEX-021": m(
        RF,
        [S],
        "The module-level functions and the methods of the classes in an outgoing adapter package. A project "
        "without a class carrying the AggregateRoot role selects nothing.",
        "No call on a name that holds an aggregate root targets a method that changes it. A name holds a root "
        "when it is a parameter or a local annotated with a class of the AggregateRoot role, is assigned a "
        "construction of one, a call of its class or static method, or a call of a method or function whose "
        "return annotation names one, is the loop variable over such a name, or is self.<attribute> typed with "
        "one. A method changes the root when it is a public instance method, neither property nor class or "
        "static method, of the root or a project class it extends, that is annotated -> None or assigns to "
        "self; a method the building blocks declare (clearing the recorded events after publishing) passes. "
        "Python has no static types: a name bound in another way is not followed. A change written to "
        "storage directly, past the aggregate, is not seen.",
    ),
    "DCA-HEX-014": m(
        RF,
        [S],
        "Handlers of GET: a function a router decorator registers - <router>.<method>(path, ...) or an imported "
        "framework <method>(path, ...), the path a literal or any expression, route/api_route with methods containing "
        "GET - and the get method of a class-based view (a class below a view-bases preset: Django's View, Flask's "
        "View and MethodView, Litestar's Controller, Starlette's HTTPEndpoint).",
        "Neither the handler nor what it calls of its own - a function of its module, a method of its view - names a "
        "command class of the application (built, taken as a parameter or annotated: a name ending with Command), or "
        "calls a method on an input port whose input is a command (I of its UseCase[I, O], or its execute's "
        "parameter), held in a parameter, an annotated local or a field of the view.",
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
        "Classes, interfaces excluded, that carry the EventListener role and not the TransactionalEventListener "
        "role - a listener that reacts inside the publishing transaction; and functions a configured "
        "listener-decorators entry registers (empty by default: Python has no common listener decorator). What "
        "reaches an input port: a field whose annotation names a class with the InputPort role, through generic "
        "arguments; a method parameter annotated so; any name of such a class in a method's body.",
        "No such listener reaches an input port: a listener that drives a use case carries the "
        "TransactionalEventListener role, so it is delivered after the commit, from the outbox, in a transaction "
        "of its own. The two building blocks are the declaration, as Java's listener annotations are. A call "
        "through a second class is not followed.",
    ),
    "DCA-HEX-018": m(
        RF,
        [S],
        "The handlers anywhere below the base package: functions a router decorator registers (as DCA-HEX-014 reads "
        "them, any HTTP method) and class-based views, once per view.",
        "Each sits in an incoming adapter package.",
    ),
    "DCA-HEX-019": m(
        AT,
        [S],
        "Classes, interfaces excluded, that carry the OutputPort role - repositories, stores and publishers "
        "included. Not selected: a class in an infrastructure package, a context's or the composition root, that "
        "itself drives an input port (names one in its fields, parameters or body, or calls execute) - the bridge "
        "that hands an output port a second use case, which is wiring.",
        "Each sits in an outgoing adapter package. DCA-TAC-015 and DCA-TAC-020 hold repositories and stores the same "
        "way in the tactical set.",
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
        "Classes that carry the AggregateRoot role, with the fields of their role-less bases.",
        "No field annotation, generic arguments included, names a class with the OutputPort role or a "
        "port building block.",
    ),
    "DCA-TAC-003": m(
        AT,
        [S],
        "Classes that carry the AggregateRoot role.",
        "No field annotation, through generic arguments, names another class with the AggregateRoot role. "
        "Fields are class-level annotations and the self.<name> assignments of every method, typed by "
        "their annotation, by the parameter assigned or by the class a call constructs; those of role-less bases "
        "count as the class's own.",
    ),
    "DCA-TAC-004": m(
        AT,
        [M, S],
        "Classes, interfaces excluded and the most derived only, that carry the Entity role.",
        "Entity declares id as an abstract property, so an entity without it cannot be built and the "
        "type checker refuses it; the source test checks that a field, its own or a base's, holds a "
        "class with the Id role, so the identity is state, not computed.",
    ),
    "DCA-TAC-005": m(
        RF,
        [S],
        "Every build of a class that carries the Entity role but not AggregateRoot: a call of the class, or "
        "dataclasses.replace / copy.replace of a parameter, an annotated local or self typed with it.",
        "It happens inside a class that carries the AggregateRoot, Entity or Factory role in a domain module of the "
        "entity's own context - the innermost class around the call. Python has no package-private constructor; the "
        "call site is what the rule reads.",
    ),
    "DCA-TAC-006": m(
        AT,
        [S],
        "Classes that carry the Entity or Value role, with the methods of their role-less bases.",
        "No method named set_<name> takes exactly one parameter and returns nothing of its class, and no property has "
        "a setter. A fluent set_<name> - returning self or annotated to return Self - is no setter.",
    ),
    "DCA-TAC-007": m(
        AT,
        [S],
        "Classes that carry the Entity role but not AggregateRoot, with the fields of their role-less bases.",
        "No field annotation, through generic arguments, names a class with the AggregateRoot role.",
    ),
    "DCA-TAC-008": m(
        AT,
        [S],
        "Classes that carry the Value role, with the fields of their role-less bases.",
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
    "DCA-TAC-011": m(
        AT,
        [S],
        "Classes that carry the Value role, with the methods of their role-less bases.",
        "No method is named set_<name>.",
    ),
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
        "Interfaces that carry the Repository role.",
        "Each sits in an application package, the shared kernel's included.",
    ),
    "DCA-TAC-015": m(
        AT,
        [S],
        "Classes, interfaces excluded, that carry the Repository role.",
        "Each sits in an outgoing adapter package. A role is nominal: an implementation names its port "
        "among its bases (DCA-PY-003).",
    ),
    "DCA-TAC-016": m(
        TC,
        [M, S],
        "Interfaces that carry the Repository role through Repository[A, K].",
        "The bound A: AggregateRoot makes a repository for anything else a type error. The source test "
        "checks the first type argument: a class with the AggregateRoot role, and the port named after "
        "it plus Repository.",
    ),
    "DCA-TAC-017": m(
        AT,
        [S],
        "Interfaces that carry the Repository role.",
        "No method's return annotation names a class with the Entity role but not AggregateRoot.",
    ),
    "DCA-TAC-018": m(
        AT,
        [S],
        "Interfaces outside every adapter (incoming and outgoing) and infrastructure package whose name ends with "
        "Store.",
        "The class carries the Store role and not the Repository role.",
    ),
    "DCA-TAC-019": m(AT, [S], "Interfaces that carry the Store role.", "Each sits in an application package."),
    "DCA-TAC-020": m(
        AT, [S], "Classes, interfaces excluded, that carry the Store role.", "Each sits in an outgoing adapter package."
    ),
    "DCA-TAC-021": m(
        AT,
        [S],
        "Interfaces that carry the Store role.",
        "No method declared on the interface itself is named save, delete or delete_by_id.",
    ),
    "DCA-TAC-023": m(
        RF,
        [S],
        "Every build of a class that carries the AggregateRoot role: a call of the class, or dataclasses.replace / "
        "copy.replace of a parameter, an annotated local or self typed with it.",
        "It happens in the module that declares the root - its class methods (create, restore, ...) "
        "build it and check its invariants. Python has no private constructor; the call site is what "
        "the rule reads.",
        title="Aggregate Roots are built through their own class methods",
    ),
    "DCA-TAC-024": m(
        AT,
        [S],
        "Classes that carry the Value role, and their public class and static methods annotated to return the class "
        "or Self.",
        "No neutral factory (of, new, create, value_of, make) takes the same parameter types - resolved names, in the "
        "same order - as another of these factories. Two named origins (from_input, from_stored) pass.",
    ),
    "DCA-TAC-025": m(
        AT,
        [S],
        "Classes in a domain package, the shared kernel's included - their fields and their methods, private ones "
        "included, dunders not. Not selected: a value or id with exactly one field, whatever its name; exceptions. An "
        "enum's members are its cases, no fields; its methods are read.",
        "No field, parameter or return annotation names str, int, float, bytes, complex, a datetime point in time "
        "(datetime, date, time) or uuid.UUID; timedelta passes, as Java's Duration does. A private bool field - a "
        "single yes/no fact - and a bool return - a predicate - pass; a bool parameter and a public bool field do not. "
        "A bool parameter of the factory that rebuilds a stored object - a class or static method annotated to return "
        "the class or Self, named as [tool.dca] reconstituting-factories lists, reconstitute and restore by default, "
        "case ignored - passes; its other parameters are checked. An enum class with exactly two members that name one "
        "fact and its negation - yes/no, true/false, on/off, present/absent, enabled/disabled, X beside NOT_X, NO_X or "
        "NON_X, or an adjective-like X (ending in -ed, -able, -ible, -ive, -ent, -ant, -al, -ful) beside UN_X, case "
        "and underscores ignored - is reported where it is declared: a boolean in disguise. LOCKED/UNLOCKED is one "
        "fact, LOCK/UNLOCK two actions; two members with names of their own pass.",
    ),
    "DCA-TAC-026": m(
        AT,
        [S],
        "The repository interfaces that bind a class with both the Owned and the AggregateRoot "
        "role as the first type argument of Repository[A, K] (or of a narrower port).",
        "The owner id type is the type argument of Owned[...] among the aggregate's bases; a bare Owned "
        "is reported. At least one method of the repository, inherited interface methods included, takes "
        "a parameter annotated with the aggregate's id type (K, or else the return of its id property) "
        "and one annotated with the owner id type, in either position, and returns an annotation that "
        "names the aggregate (itself, Optional, a list ...). A method answering bool does not count. "
        "Whether a use case calls the scoped lookup is not checked.",
    ),
    "DCA-TAC-027": m(
        AT,
        [S],
        "Classes, interfaces excluded, that carry the AggregateRoot, Entity, Value, Factory or Specification role, "
        "and classes whose name ends with Specification; a class that itself carries the DomainGateway role is "
        "not selected. Read: the class body - its fields, its class-level assignments, its methods' return "
        "annotations and their bodies. A nested class is a class of its own.",
        "A class that names DomainGateway or carries its role, through generic arguments, appears in none of "
        "these places: a field annotation, class-level or self.<name> in any method typed by its annotation or by "
        "the parameter assigned; an assignment of a gateway parameter to self.<name> in any method; a class "
        "attribute bound to a gateway; a method's return annotation; a name in a method body that hands out a "
        "gateway without a parameter - a module variable annotated with one or bound to a built implementation, "
        "a class attribute annotated with one, a function or method whose return annotation is one (a registry "
        "or locator); a call that builds a class with the DomainGateway role. A gateway taken as a parameter of "
        "__init__ or of a method and the calls made on it pass - __init__ that keeps it on self is reported for "
        "the field. A domain service and the application may use the gateway freely. A value whose type is not "
        "written out - an unannotated local, an untyped return - is not followed.",
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
        "Every module in a context's application package. A context is a package directly below the base package; "
        "deeper nesting is not read.",
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
        "Classes that carry the OpenHostService role, and modules that declare one: an open host service of "
        "functions marks its package with __dca__ = OpenHostService() in its __init__.py.",
        "Each sits in an api package or in an incoming adapter package.",
    ),
    "DCA-STR-006": m(
        AT,
        [IMP],
        "Every module in a context's adapter packages.",
        "An import of another context names that context's api or events package only.",
    ),
    "DCA-STR-007": m(
        AT,
        [S],
        "Classes that carry the IntegrationEvent role.",
        "Each sits in a context's events package, a sibling of its api package as Java's "
        "{context}/events beside {context}/api; never in the shared kernel, which has no events package, "
        "and never in api.",
    ),
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
        "The packages directly below the base package - the only depth a bounded context is read at.",
        "At least one declares __dca__ = BoundedContext(...) in its __init__.py. "
        "A project that holds no production code yet passes. It holds none while no module below the base package "
        "holds a statement besides its docstring, a program entry point aside: an empty __init__.py is no code, nor "
        "is a module whose statements are a docstring, imports, at most one function named main and the guard if "
        "__name__ == '__main__': whose body only calls or raises (a module named __main__ may call or raise at the "
        "top level as well); tests outside the package are not read, tests inside it count as code. "
        "Once one such statement exists, the rule fails until a context is declared, so a base package or a layout "
        "that misses the declarations still fails.",
    ),
    "DCA-STR-012": m(
        AT,
        [S],
        "Every module below the base package.",
        "At least one sits in a DCA layer of a context or of the shared kernel; the composition root alone does not "
        "count. "
        "A project that holds no production code yet passes. It holds none while no module below the base package "
        "holds a statement besides its docstring, a program entry point aside: an empty __init__.py is no code, nor "
        "is a module whose statements are a docstring, imports, at most one function named main and the guard if "
        "__name__ == '__main__': whose body only calls or raises (a module named __main__ may call or raise at the "
        "top level as well); tests outside the package are not read, tests inside it count as code. "
        "Once one such statement exists, the rule fails until a module sits in a layer, so a layout that misses the "
        "existing code still fails.",
    ),
    "DCA-STR-013": m(
        AT, [S], "Classes in a context's events package, enums excluded.", "Each carries the IntegrationEvent role."
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
        reason="No preset yet: a second module declaration exists in Python only as a tool's own file (a uv "
        "workspace member per context, tach.toml), and the suite reads none of them; __dca__ is the declaration, "
        "and DCA-MAP-007/011 compare it with the imports.",
    ),
    "DCA-MAP-007": m(
        RF,
        [S, IMP],
        "Every implemented Upstream of a context's declaration.",
        "For each channel, a module of the declaring context imports the target's api (api channel) or "
        "events (events channel) package.",
    ),
    "DCA-MAP-008": m(
        RF,
        [IMP],
        "Every Upstream declaration with Translation.ANTI_CORRUPTION_LAYER towards a declared context, and the imports "
        "into that context's api or events package; an import is judged by the declaration of its channel.",
        "Placement, whatever the status: the api channel is imported only by the outgoing adapters, the events channel "
        "only by the incoming adapters. Presence, unless the status is PLANNED: each declared channel has a module in "
        "the matching adapter that imports both the channel and its own context's domain or application.",
    ),
    "DCA-MAP-009": m(
        RF,
        [IMP],
        "Imports into another context's api or events package by a context that declares it with "
        "Translation.CONFORMIST.",
        "None comes from a domain module.",
    ),
    "DCA-MAP-010": m(
        RF,
        [IMP],
        "Imports of the contract_packages an ExternalUpstream names - the module imported or a name imported from "
        "above it (from vendor import sdk reaches vendor.sdk).",
        "With an anti-corruption layer only the matching adapter imports them (outgoing for OUTBOUND, "
        "incoming for INBOUND); with conformist, no domain module does.",
    ),
    "DCA-MAP-011": m(
        RF,
        [IMP],
        "Every import of a context's module into another context's api or events package.",
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
        reason="No preset yet: a module declaration with allowed dependencies exists in Python only as a tool's own "
        "file (a uv workspace member per context, tach.toml), and the suite reads none of them; DCA-MAP-007 "
        "requires every edge __dca__ declares to be backed by an import.",
    ),
    # --- advanced ----------------------------------------------------------------------------------------------
    "DCA-ADV-001": m(
        RF,
        [R, S],
        "Classes in a domain package whose name ends with Event, and classes that carry the DomainEvent role.",
        "A class named an event carries the DomainEvent role - an IntegrationEvent does not count; an event is a "
        "frozen dataclass by its base, holds no mutable collection (its role-less bases' fields included), and no "
        "method other than __init__, __post_init__ and __new__ assigns to self or calls object.__setattr__, nor does "
        "the class define __setattr__.",
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
        "Classes that carry the IntegrationEvent role, with the fields of their role-less bases.",
        "No field is named schema_version, event_version or contract_version.",
    ),
    "DCA-ADV-007": m(
        AT,
        [S],
        "Classes that carry the DomainEvent role but not IntegrationEvent, with the fields of their role-less bases.",
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
        "Classes that carry the DomainService role, with the methods of their role-less bases.",
        "No method other than __init__, __post_init__ and __new__ assigns to self (directly or through an alias of "
        "self) or calls object.__setattr__, and the class defines no __setattr__. Python has no final field; "
        "statelessness is the absence of mutation.",
    ),
    "DCA-ADV-013": m(AT, [S], "Classes that carry the Factory role.", "The name ends with Factory."),
    "DCA-ADV-014": m(AT, [S], "Classes that carry the Factory role.", "Each sits in a domain package."),
    "DCA-ADV-015": m(AT, [S], "Classes in a domain package that carry the Factory role.", META_CHK),
    "DCA-ADV-016": m(
        RF,
        [S],
        "Classes that carry the Factory role, with the methods of their role-less bases.",
        "No method other than __init__, __post_init__ and __new__ assigns to self (directly or through an alias of "
        "self) or calls object.__setattr__, and the class defines no __setattr__.",
    ),
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
        "Methods of classes that carry the Entity or Value role, those of role-less bases included.",
        "No method constructs a class with the DomainService role or calls one - on its class, on a parameter or local "
        "that holds one (an alias included), or on self.<attribute>. Holding one alone is not reported.",
    ),
    "DCA-ADV-020": m(
        AT,
        [S],
        "Public methods of classes that carry the DomainService role.",
        "At least one parameter's annotation names a class with the Entity role.",
    ),
    "DCA-ADV-021": m(
        AT,
        [S],
        "Every module outside an application package and the building blocks: its module-level statements, its "
        "functions and the methods of its classes, a class with the DomainService role excluded. A domain service is "
        "a class with the DomainService role, as DCA-ADV-010 selects it: roles are nominal on classes, so a module of "
        "functions is no domain service by this rule. A project without a class of that role selects nothing.",
        "No call constructs a class with the DomainService role, calls a function on it, or calls a method on a "
        "parameter or a local or module-level name annotated with it, assigned a construction of it or an alias of "
        "one, on a "
        "self.<attribute> typed with it or assigned one, or on one built in place. In an infrastructure package - the "
        "context's or the project's, the composition root - a construction (the class called, or a class or static "
        "method annotated to return it) passes; a call there is reported. A parameter of that type alone is not "
        "reported; a call through a name the suite cannot type is not seen.",
    ),
    # --- use case ----------------------------------------------------------------------------------------------
    "DCA-USE-001": m(AT, [S], "Classes named InputPort below the base package.", "There is none."),
    "DCA-USE-002": m(
        AT, [S], "Classes whose name ends with Command, values included.", "Each sits in an application package."
    ),
    "DCA-USE-003": m(
        AT, [S], "Classes whose name ends with Query, values included.", "Each sits in an application package."
    ),
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
        "Classes whose name ends with Result and that do not carry the Value role - a result may be a domain value; "
        "a Command, a Query or a Response named so is selected as a value too.",
        "Each sits in an application package.",
    ),
    "DCA-USE-007": m(
        RF,
        [S],
        "Classes in an application package whose name ends with Result.",
        "Each is a frozen dataclass, a NamedTuple or an enum, and holds no mutable collection. A case of a "
        "closed result need not be named ...Result; the union alias is.",
    ),
    "DCA-USE-008": m(
        AT, [S], "Classes whose name ends with Response, values included.", "Each sits in an adapter package."
    ),
    "DCA-USE-009": m(
        RF,
        [S],
        "Use cases: classes, interfaces excluded, that carry the InputPort role.",
        "Each entry point - a public method - that calls save on a Repository, itself or through the methods of its "
        "own it names on self, transitively, also reaches a call of publish_and_clear_events on a "
        "DomainEventPublisher. A receiver is self.<attribute> (of the class or a base), a typed parameter or local, "
        "or a local alias of one.",
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
        "Every call of save, delete or delete_by_id on a Repository and of publish... on a DomainEventPublisher - "
        "receivers read as DCA-USE-009 reads them - sits inside the work the use case hands to "
        "TransactionBoundary.in_transaction or in_transaction_closed (awaited for AsyncTransactionBoundary) (a "
        "lambda, a nested function or a method of "
        "its own), or in a method of its own that only such work runs, transitively. A method an entry point also "
        "runs outside the work, and one nothing runs, is outside. The explicit boundary is the only form.",
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
    "DCA-USE-016": m(
        AT,
        [S],
        "Use cases.",
        "None depends on another input port - in a field, a parameter, an annotated local or a name its methods "
        "mention - directly, or through a class of its own module in the application. Its own interfaces and bases "
        "are excluded. Messages read Caller -> Target [via Helper].",
    ),
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
        "Use cases whose input - a parameter of execute, or I of the UseCase[I, O] they name among their bases, "
        "transitively - is a class whose name ends with Query.",
        "No call of a write on a Repository or Store - a method named, or starting with, save, delete, remove, add, "
        "insert, update, upsert, put, store, write, create, append, archive, purge, clear, set or mark and an "
        "underscore - and no call at all on a DomainEventPublisher or IntegrationEventPublisher; receivers read as "
        "DCA-USE-009 reads them.",
    ),
    "DCA-USE-020": m(
        AT,
        [S, F],
        "Every module in an application package.",
        "No call of uuid.UUID(...). Parsing happens in the adapter or in the "
        "id's own constructor; a per-directory ruff.toml (banned-api uuid.UUID) holds it while editing.",
    ),
    "DCA-USE-021": m(
        RF,
        [S],
        "Use cases: classes, interfaces excluded, that carry the InputPort role, with the methods of their role-less "
        "bases.",
        "No method other than __init__, __post_init__ and __new__ assigns to self (directly or through an alias of "
        "self) or calls object.__setattr__, and the class defines no __setattr__. Python has no final field; "
        "statelessness is the absence of mutation.",
    ),
    "DCA-USE-022": m(
        AT,
        [S],
        "Classes and interfaces with the InputPort role that name UseCase[I, O] among their bases.",
        "O, or a member of a union or Optional it names, is none of int, str, bool, float, bytes. None passes - a "
        "command with nothing to answer -, and so does a container such as list[str].",
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
        "Interfaces in an application package that carry the InputPort role.",
        "The name ends with InputPort.",
    ),
    "DCA-NAM-004": m(
        AT,
        [S],
        "Interfaces in an application package whose name contains Repository, one named exactly Repository excluded; "
        "by name alone.",
        "The name ends with Repository.",
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
        "Every module below the base package, the composition root included.",
        "No segment of its name below the base package - a namespace package's included - is entities, entity, "
        "value_objects, valueobjects, helpers, helper, util or utils.",
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
        "Input ports and use cases in an application package: classes and interfaces with the InputPort role, and "
        "classes whose name ends with the use-case suffix.",
        "Informational - lists a name that, with the use-case suffix or InputPort removed, holds On, After, When, "
        "Upon or Before at its start or after a lower-case letter or digit, followed by a capital, and never fails. "
        "OnboardMember and SignOn are not listed.",
    ),
    "DCA-NAM-013": m(
        AT,
        [S],
        "Input ports and use cases in an application package (as DCA-NAM-012 selects them), and the modules of an api "
        "package - their public functions and the public methods of their classes. The events package is not selected.",
        "No class name, with the use-case suffix or InputPort removed, starts with Set or Update followed by a "
        "capital, and no function or method name starts with set_ or update_.",
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
        "One slice per operation root of a context's application: the deepest module or package, operation "
        "containers skipped, that declares an input port or a use case (by role or by the use-case suffix); a "
        "module below it joins it. A module on the way to an operation root that is none itself is the feature "
        "slice of its first segment. The shared package and modules directly in application belong to no slice.",
        "The slices import each other in no cycle. A package's __init__ importing a module below itself re-exports "
        "it and is no dependency.",
    ),
    # --- errors ------------------------------------------------------------------------------------------------
    "DCA-ERR-001": m(
        AT,
        [S],
        "Exception classes in a domain package: those that extend any built-in exception (Exception, ValueError, ...) "
        "or carry a failure role.",
        "Each carries the DomainException role.",
    ),
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
        "Exception classes in an application package - extending any built-in exception or carrying a failure role - "
        "that do not carry DomainException.",
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
        "The name contains none of Http, HTTP, StatusCode, ResponseStatus, ResponseEntity. The bare words Status and "
        "Response are not matched: transport and domain words alike. Java's check that the name ends with none of "
        "Error, Fault, Failure is not made: PEP 8 names an exception with the suffix Error.",
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
        "Classes that carry DomainException or PortException, and their fields - those of role-less bases included.",
        "Informational - lists every field whose annotation names, containers and typing constructs looked through, "
        "a str, an entity or any other type that is neither an id nor a value, nor a number (int, float, complex, "
        "Decimal, Fraction), a bool, an enum or a date and time type of the standard library, and never fails.",
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
        "Every construction of a class with the DomainException role in a module outside the domain packages: a call "
        "of the class, or raise naming the class itself.",
        "There is none - only the domain constructs a domain exception. Re-raising one the "
        "application caught is no construction.",
    ),
    "DCA-ERR-010": m(
        AT,
        [S],
        "Every try statement (except* included) in a module of an application package or of an incoming adapter "
        "package - in a module-level function or a method, nested functions included - whose try part calls a "
        "method on a port: a parameter or an annotated local whose annotation names a class with the InputPort or "
        "OutputPort role, a local alias of one, or self.<field> typed so (a base's field included).",
        "No except clause of such a try names everything: a bare except:, Exception or BaseException, nor the "
        "port failures' common base - PortException, InputPortException or a class of the project that carries "
        "them without UseCaseException or OutputPortException; a subclass of UseCaseException or "
        "OutputPortException, UseCaseException and OutputPortException themselves and a named domain failure "
        "pass. A clause that hands the caught failure on unchanged passes - it may clean up first: it ends in a "
        "bare raise or raise <the caught name> without a cause, and no return, break or continue of its own "
        "leaves it another way; a raise ... from it wraps the failure and is reported. A try part that reaches a "
        "port through a helper of its own, through a value whose type is not written out or through a field of a "
        "parameter is not selected; a catch outside these layers passes.",
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
        title="A port is implemented by name",
        rationale="A Protocol is structural: an adapter fits a port without naming it, and the rules - which read "
        "roles from bases - lose the implementation, and with it the placement rules. A port nobody names "
        "is a port the rules cannot follow to its adapter. That holds for every port the building blocks "
        "declare: an output port of the application and a domain gateway of the domain alike.",
        category=AT,
        enforcement=[S],
        selects="Interfaces that carry the OutputPort or the DomainGateway role, and the classes of "
        "the outgoing adapters and the composition root.",
        checks="Every port is named among the bases of some class or of a narrower port; no class of the outgoing "
        "adapters or the composition root that names no port fits a port's methods, by name and parameter "
        "names - nor the methods of a building block's port (Repository, DomainEventPublisher, TransactionBoundary, "
        "AsyncTransactionBoundary). "
        "A class that names a port and fits another one by its shape is held to the port it names.",
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
        checks="No async def and no import of asyncio, trio or anyio, outside the classes that carry the "
        "DomainGateway or the DomainService role (as DCA-ONI-004 reads it).",
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
    dict(
        id="DCA-PY-008",
        title="A use case is implemented by name",
        rationale="UseCase is a Protocol: a class with an execute method fits an input port without naming it, and "
        "the rules - which read roles from bases - see no use case at all; every rule over use cases then selects "
        "nothing. An input port nobody names is a port the rules cannot follow to its use case.",
        category=AT,
        enforcement=[S],
        selects="Interfaces that carry the InputPort role, and the classes of the application with an execute method.",
        checks="Every input port is named among the bases of some class or of a narrower port; every class of the "
        "application with an execute method names an input port among its bases.",
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
