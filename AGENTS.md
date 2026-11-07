# AGENTS.md

Guidance for AI coding agents working in `dca-python` — the Python variant of `dca-java`, `dca-dotnet` and
`dca-rust`: `dca-building-blocks` (the marker classes) and `dca-rules` (the rule suite, same rule ids, read from the
source with `ast`). Unpublished; planning WP-187. `README.md` explains the distributions.

## Principles that apply in every DCA repository

These hold for anyone working in any of the DCA repositories — human or agent — regardless of local tooling or memory.

1. **The samples exist to make the AI harness deterministic, not to ship features.** They are the experiment field
   for the harness: knowledge catalog, architecture rules, markers, plugins. Every architectural change in a sample
   answers three questions before it is done — does the catalog need a node (pitfall / decision / recipe /
   template)? could a rule check it (same rule id in every DCA language)? would one more *generic* marker in the
   building blocks make it checkable? Record the answer, "none" included, in the WP or ADR. Two agents building the
   same thing differently in the two samples is a determinism gap to close at the source (catalog, rule, marker),
   not with a code fix.
2. **Rules, markers and the catalog are general.** They are the foundation other production systems — any industry —
   build on with AI. Nothing in them may exist only because a sample needs it: no shop or todo vocabulary in rule or
   marker names or texts, no selection that only matches a sample's layout, no catalog node that presupposes a cart.
   The sample proves the general artifact; it is never its source of names or shapes.
3. **The core libraries are framework-neutral.** Both distributions depend on the standard library only; the rules
   name frameworks (FastAPI, Django, Flask, SQLAlchemy, Pydantic, …) only as configurable presets in
   `dca_rules/layout.py` and never import them. Framework-specific code goes into a satellite or into a sample.
4. **Each reader artifact stands alone.** Guide, book and catalog bundle are independently readable; links never
   cross repository boundaries (the sample may cite the guide). `AGENTS.md` files are exempt — they carry the
   cross-project pointers and the sync duties.

## Working here

- **Build:** `uv sync`, then `uv run pytest -q`, `uv run mypy` (strict, from `pyproject.toml`), `uv run ruff check .`,
  `uv run ruff format --check .` — the same four run in the `Dockerfile`.
- **The rule catalog:** `dca-rules/src/dca_rules/rules.json` holds every DCA id with its Python meaning (category,
  enforcement levels, `selects`/`checks`, whether the suite implements it). It is written by
  `uv run python dca-rules/mapping/map_rules.py ../dca-java/rules.json dca-rules/src/dca_rules/rules.json` —
  titles and rationales come from the Java list, so an id keeps one meaning; the Python readings live in the script,
  and which ids are implemented is read from the suite's registry. Regenerate it with every rule change and whenever
  `dca-java/rules.json` gains an id (the script fails until the mapping has it).
- **A new rule** is a function with `@rule("DCA-XXX-nnn")` in the matching `dca-rules/src/dca_rules/rules/<set>.py`,
  a violation in `dca-rules/fixtures/violations` on a line marked `# DCA-XXX-nnn`, and nothing that fires in
  `dca-rules/fixtures/conforming` — `tests/test_fixtures.py` fails otherwise. Python-only rules take the next
  `DCA-PY-nnn` in `rules/python.py` and the mapping's `PYTHON_ONLY`, and start `experimental`.
- **Roles are nominal.** A rule selects by the building blocks named among a class's bases, transitively, never by a
  structural fit; `DCA-PY-003` holds the project to it. Fields are class-level annotations plus the `self.<name>`
  assignments of `__init__`, typed by their annotation or by the parameter assigned.
- **Fixtures** are read, never imported or run; they name contexts `alpha` … `zeta` and types like `Thing` and `Part`
  — no vocabulary of a sample.
- **The building blocks have no dependencies.** `EventId` and `Timestamp` are their own values so a domain field
  never holds a bare `uuid.UUID` or `datetime`.
- **Consumers:** the todo app the suite was proven on (outside this repository) depends on both distributions by
  path. A change to a rule runs its architecture tests there too.

## Commit message format

Conventional commits, the scope naming the distribution: `feat(dca-rules): …`, `fix(dca-building-blocks): …`.
