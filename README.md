# dca-python

*Written with AI assistance — drafted mainly by Claude, reviewed and directed by Christoph Bloemer since
2025. The architecture rules in this repository's tests are part of how that work is verified.*

Architecture rules for Domain-Centric Architecture in Python: the same rule ids as the Java, .NET and Rust
suites, read from the source with `ast`, plus the building blocks they read the roles from. Standard library only,
Python 3.12 or newer.

| Distribution | What it is |
|---|---|
| `dca-building-blocks` | the marker classes — `Value`, `Id`, `Entity`, `AggregateRoot`, `Owned`, `DomainEvent`, `IntegrationEvent`, `DomainService`, `Factory`, `Specification`, `DomainException`, `InputPort`, `UseCase`, `OutputPort`, `Repository`, `Store`, the publishers, `TransactionBoundary`, `Refusal`, `UseCaseException`, `OutputPortException` (port exceptions, classified as `PortException`), `OpenHostService`, and the declarations `BoundedContext`, `Upstream`, `ExternalUpstream`, `Partnership`, `SharedKernel` |
| `dca-rules` | the rule suite: `rules.json` (every DCA id with its Python meaning), the rules, a pytest entry and a command line |

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

`python -m dca_rules [pyproject.toml] [DCA-…]` prints the same from the command line. Closed use-case results —
`type ReserveResult = Reserved | SeatTaken` with the refusal marked `Refusal` — are checked for exhaustiveness by
the type checker, so a project runs `mypy --strict` (or pyright) beside the suite and ends every match over a
result with `case _: assert_never(result)`. Experimental rules run only where `[tool.dca] experimental` names
them. Not yet on PyPI; proven on a todo app.

## Author

**Christoph Bloemer** — [@chbloemer](https://github.com/chbloemer)

## License

MIT — see [LICENSE](LICENSE).

Contributions are accepted under the MIT licence, and the copyright holder may additionally publish
them under other licences (for example a documentation licence for prose).
