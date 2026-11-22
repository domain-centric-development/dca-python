# dca-python

*Written with AI assistance — drafted mainly by Claude, reviewed and directed by Christoph Bloemer since
2025. The architecture rules in this repository's tests are part of how that work is verified.*

Architecture rules for Domain-Centric Architecture in Python: the same rule ids as the Java, .NET and Rust
suites, read from the source with `ast`, plus the building blocks they read the roles from. Standard library only,
Python 3.12 or newer.

| Distribution | What it is |
|---|---|
| `dca-building-blocks` | the marker classes — `Value`, `Id`, `Entity`, `AggregateRoot`, `Owned`, `DomainEvent`, `IntegrationEvent`, `DomainService`, `DomainGateway`, `Factory`, `Specification`, `DomainException`, `InputPort`, `UseCase`, `OutputPort`, `Repository`, `Store`, the publishers, `TransactionBoundary`, `EventListener` and `TransactionalEventListener`, `Refusal`, `UseCaseException`, `OutputPortException` (port exceptions, classified as `PortException`), `OpenHostService`, and the declarations `BoundedContext`, `Upstream`, `ExternalUpstream`, `Partnership`, `SharedKernel` |
| `dca-rules` | the rule suite: `rules.json` (every DCA id with its Python meaning), the rules, a pytest entry and a command line |

A context publishes in two packages, as Java keeps `{context}/api` and `{context}/events` side by side: `api/`
holds the operations other contexts call (an open host service), `events/` the integration events they consume.
The shared kernel has the layers of a context — `domain/`, `application/`, `adapter/`, `infrastructure/` — and
neither `api/` nor `events/`: shared domain objects, shared ports and their technical adapters, a shared outbox for
instance. Every context may use it layer by layer; it uses no context.

Events reach other listeners in two ways. An `EventListener` reacts inside the publishing transaction and writes
through output ports only. A `TransactionalEventListener` reacts after the commit, in a transaction of its own. How the
delivery survives a crash - an outbox, a relay, a record of receipts - is the adapters' concern, not a building block;
the example keeps it in its shared kernel.
A listener that drives a use case is always of the second kind (`DCA-HEX-017`). The domain is synchronous, except a
domain gateway that answers asynchronously and a domain service that awaits it (`DCA-ONI-004`).

A class takes a role by naming the building block among its bases — a role is always nominal, so an adapter names
the port it implements even where a `Protocol` would let it fit by shape. `Value`, `Id` and the events are frozen
dataclasses by their base:

```python
class ThingId(Id):
    value: str


class Thing(AggregateRoot[ThingId], Owned[OwnerId]): ...


class ThingRepository(Repository[Thing, ThingId], Protocol):
    def find_for_owner(self, thing_id: ThingId, owner: OwnerId, /) -> Thing | None: ...


class InMemoryThingRepository(ThingRepository): ...
```

A project names its layout in `pyproject.toml`, each bounded context declares itself in its package, and one test
module runs the suite:

```toml
[tool.dca]
base-package = "orders"      # src/orders/<context>/{domain, application, adapter/{incoming,outgoing}, api}
experimental = ["DCA-PY-004"]  # or "all"
```

A tool that may not depend on the distribution keeps its own copy of the markers and names it:
`building-blocks = ["orders.building_blocks"]` — the copy then counts as `dca_building_blocks` and is not read as a
module of the project.

```python
# src/orders/billing/__init__.py
__dca__ = BoundedContext(name="billing")

# tests/architecture/test_architecture.py
from dca_rules.testing import architecture_tests

test_dca = architecture_tests("pyproject.toml")  # one case per rule id: test_dca[DCA-TAC-003], …
```

A violation fails its case with one line per finding, the rule id first:

```
[DCA-TAC-003] src/orders/billing/domain/invoice.py:14: Invoice.customer holds the aggregate root Customer; reference another aggregate by its id
```

A rule selects the elements of the concept it governs — by role, by layer or by name — and holds over them. Where
it selects nothing, it did not hold: it reports `nothing selected` and fails its case, so a missing marker cannot
pass as green. A project that has none of a concept on purpose says so once, with the reason:

```toml
[tool.dca]
allow-empty = [
    { rule = "DCA-ADV-013", reason = "every aggregate is built by its own class; no factory" },
]
```

A project that holds no production code yet - no module below the base package holds a statement besides its
docstring - has nothing to select: there every empty selection passes without `allow-empty`, and the suite is green.
Once one such statement exists, an empty selection fails again.

Every package name and suffix the suite places or selects by is renamed in the same table, as Java's `DcaLayout`
renames packages and suffixes; each value is one identifier, and one that is none fails the load:

```toml
[tool.dca]
domain = "domain"                      # the packages, by their defaults
application = "application"
shared = "shared"                      # the shared output ports in application/
adapter = "adapter"
incoming = "incoming"
outgoing = "outgoing"
event = "event"                        # event consumers in incoming/
web = "web"                            # server-rendered adapters in incoming/
api = "api"
events = "events"
shared-kernel = "sharedkernel"
infrastructure = "infrastructure"
operation-containers = []              # application packages that only group operations
use-case-suffix = "UseCase"
input-port-suffix = "InputPort"
aggregate-root-suffix = "AggregateRoot"
repository-suffix = "Repository"
store-suffix = "Store"
factory-suffix = "Factory"
specification-suffix = "Specification"
```

The presets the rules read are replaced or extended the same way: `frameworks` (or `extra-frameworks`),
`allowed-in-domain`, `timestamp-types`, `reconstituting-factories`, `router-methods`, `authorization-decorators`,
`listener-decorators`, `async-types`, `async-runtimes` and `persistence-apis`; each rule's `selects` in `rules.json`
names the key it reads and its default.

Java's controller suffixes have no counterpart: a handler is found by its router decorator (`router-methods`), not
by its name.

An open host service of functions — an `api` package without a facade class — declares itself in its package, as a
context does: `__dca__ = OpenHostService()` in its `__init__.py`.

`python -m dca_rules [pyproject.toml] [DCA-…]` prints the same from the command line. Closed use-case results —
`type ReserveResult = Reserved | SeatTaken` with the refusal marked `Refusal` — are checked for exhaustiveness by
the type checker, so a project runs `mypy --strict` (or pyright) beside the suite and ends every match over a
result with `case _: assert_never(result)`. Experimental rules run only where `[tool.dca] experimental` names
them. Not yet on PyPI; proven on a todo app. `example/` is a small runnable library application - two contexts and
a shared kernel - that uses every building block, the outbox, its relay and the inbox included, with the rule suite
green on it.

## Author

**Christoph Bloemer** — [@chbloemer](https://github.com/chbloemer)

## License

MIT — see [LICENSE](LICENSE).

Contributions are accepted under the MIT licence, and the copyright holder may additionally publish
them under other licences (for example a documentation licence for prose).
