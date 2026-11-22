"""Every implemented rule fires on the line a fixture marks with its id, none fires on the conforming fixture, and the
roles the rules select by are found.

`fixtures/violations` holds at least one violation per rule, its line marked `# DCA-XXX-nnn`; `fixtures/undeclared`
is a project without a context or a layer; `fixtures/conforming` follows every rule. None is ever run.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import subprocess
import sys

import pytest
from dca_rules import NO_PRODUCTION_CODE, Finding, catalogue, implemented, report, run
from dca_rules.layout import DcaLayout
from dca_rules.model import Project

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
#: Rules that select nothing (doctrine only) or list what exists rather than what is wrong.
NOTHING_TO_FIND = {"DCA-LAY-001", "DCA-STR-010"}
LISTINGS = {"DCA-STR-001", "DCA-MAP-013"}


def fixture(name: str) -> Project:
    project = Project(DcaLayout.from_pyproject(FIXTURES / name / "pyproject.toml"))
    assert not project.problems
    return project


def findings(project: Project, rule_id: str) -> tuple[Finding, ...]:
    outcome = run(project, rule_id)
    assert outcome.kind in ("ran", "empty"), f"{rule_id} did not run: {outcome.kind}"
    return outcome.findings


def marked(name: str, finding: Finding, rule_id: str) -> bool:
    path, _, line = finding.location.rpartition(":")
    if not line.isdigit():
        return True  # a finding about the whole project
    lines = (FIXTURES / name / path).read_text(encoding="utf-8").splitlines()
    return rule_id in lines[int(line) - 1]


def test_every_implemented_rule_fires_on_a_line_marked_with_its_id() -> None:
    silent, unmarked = [], []
    projects = {name: fixture(name) for name in ("violations", "undeclared")}
    for rule_id in implemented():
        if rule_id in NOTHING_TO_FIND:
            continue
        found = [(name, f) for name, p in projects.items() for f in findings(p, rule_id)]
        if not found:
            silent.append(rule_id)
        elif rule_id not in LISTINGS and not any(marked(name, f, rule_id) for name, f in found):
            unmarked.append(f"{rule_id}: {[f.location for _, f in found]}")
    assert not silent, f"rules that found nothing in the fixtures: {silent}"
    assert not unmarked, "rules that found something, never on a line marked with their id:\n" + "\n".join(unmarked)


def test_no_rule_finds_anything_in_the_conforming_fixture() -> None:
    project = fixture("conforming")
    found = [
        f"[{r}] {f.location}: {f.message}" for r in implemented() if r not in LISTINGS for f in findings(project, r)
    ]
    assert not found, "findings in a project that follows every rule:\n" + "\n".join(found)


def test_a_reconstituting_factory_takes_its_yes_no_fact_back() -> None:
    lamp = [f.message for f in findings(fixture("violations"), "DCA-TAC-025") if f.message.startswith("Lamp.")]
    assert "Lamp.restore(hours) takes int" in lamp
    assert "Lamp.switch(lit) takes bool" in lamp
    assert not [m for m in lamp if m.startswith("Lamp.restore(lit)")]


def test_a_domain_service_is_used_by_the_application_only() -> None:
    found = [f.message for f in findings(fixture("violations"), "DCA-ADV-021")]
    assert any(m.startswith("export calls pricing.price") for m in found), found
    assert any(m.startswith("minimum calls PRICING.price") for m in found), found
    assert any(m.startswith("Part.price calls Pricing.price") for m in found), found
    assert not [m for m in found if m.startswith("fx.alpha.infrastructure.config constructs")], found
    assert not [m for m in found if "AppService" in m], found


def test_the_reconstituting_factory_follows_the_configured_names() -> None:
    layout = DcaLayout.from_pyproject(FIXTURES / "conforming" / "pyproject.toml")
    renamed = Project(dataclasses.replace(layout, reconstituting_factories=("rehydrate",)))
    assert [f.message for f in findings(renamed, "DCA-TAC-025")] == ["Thing.reconstitute(archived) takes bool"]


def test_a_rule_finds_something_only_among_what_it_selected() -> None:
    projects = {name: fixture(name) for name in ("violations", "undeclared", "own-markers")}
    found_over_nothing = [
        f"{name}: {rule_id}"
        for name, project in projects.items()
        for rule_id in implemented()
        if (outcome := run(project, rule_id)).findings and outcome.selected == 0
    ]
    assert not found_over_nothing


def test_the_conforming_fixture_names_exactly_what_it_lacks() -> None:
    project = fixture("conforming")
    empty = {r for r in implemented() if run(project, r).kind == "empty"}
    allowed = {r for r, _ in project.layout.allow_empty}
    assert empty == allowed, (
        f"select nothing: {sorted(empty - allowed)}; allowed, select something: {sorted(allowed - empty)}"
    )


def test_a_rule_that_selects_nothing_is_its_own_outcome_and_fails() -> None:
    source = DcaLayout.from_pyproject(FIXTURES / "conforming" / "pyproject.toml")
    bare = Project(DcaLayout(project_root=source.project_root, base_package="fx", experimental="all"))
    outcome = run(bare, "DCA-NAM-007")
    assert (outcome.kind, outcome.selected, outcome.findings, outcome.allowed) == ("empty", 0, (), None)
    assert outcome.fails
    assert "nothing selected" in report("DCA-NAM-007", outcome)
    assert run(bare, "DCA-TAC-003").selected > 0


def test_allow_empty_with_a_reason_lets_a_rule_select_nothing() -> None:
    outcome = run(fixture("conforming"), "DCA-NAM-007")
    assert outcome.kind == "empty" and outcome.allowed and not outcome.fails
    assert f"allowed: {outcome.allowed}" in report("DCA-NAM-007", outcome)


def test_allow_empty_without_a_reason_is_refused(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="reason"):
        DcaLayout(project_root=tmp_path, base_package="fx", allow_empty=(("DCA-NAM-007", " "),))
    (tmp_path / "pyproject.toml").write_text(
        '[tool.dca]\nbase-package = "fx"\nallow-empty = [{ rule = "DCA-NAM-007" }]\n'
    )
    with pytest.raises(ValueError, match="reason"):
        DcaLayout.from_pyproject(tmp_path / "pyproject.toml")


def test_a_rule_of_doctrine_alone_selects_nothing_by_design() -> None:
    outcome = run(fixture("conforming"), "DCA-LAY-001")
    assert outcome.kind == "ran" and outcome.selected == 0 and not outcome.fails


def test_a_domain_gateway_is_implemented_by_name() -> None:
    messages = [f.message for f in findings(fixture("violations"), "DCA-PY-003")]
    assert "no class names the domain gateway Ratings among its bases" in messages
    assert any(m.startswith("ShapeRatings fits the domain gateway Ratings by its shape") for m in messages)


def test_an_open_host_service_of_functions_is_declared_by_its_module() -> None:
    conforming = run(fixture("conforming"), "DCA-STR-005")
    assert conforming.selected == 2 and not conforming.findings
    found = findings(fixture("violations"), "DCA-STR-005")
    assert any(f.location == "src/fx/alpha/domain/rating.py:5" for f in found), found


@pytest.mark.parametrize(
    ("name", "role"),
    [
        ("alpha.domain.thing.Thing", "AggregateRoot"),
        ("alpha.domain.thing.Thing", "Entity"),
        ("alpha.domain.thing.Thing", "Owned"),
        ("alpha.domain.thing.Part", "Entity"),
        ("alpha.domain.thing.Label", "Value"),
        ("alpha.domain.thing.ThingId", "Id"),
        ("alpha.domain.thing.ThingId", "Value"),
        ("alpha.domain.thing.PartAdded", "DomainEvent"),
        ("alpha.domain.thing.ThingFull", "DomainException"),
        ("alpha.domain.sizing.Balancing", "DomainService"),
        ("alpha.domain.sizing.ThingFactory", "Factory"),
        ("alpha.domain.sizing.FullThingSpecification", "Specification"),
        ("alpha.application.shared.ThingRepository", "Repository"),
        ("alpha.application.shared.ThingRepository", "OutputPort"),
        ("alpha.application.shared.ThingJournal", "Store"),
        ("alpha.application.shared.BetaUnavailable", "OutputPortException"),
        ("alpha.application.add_part.AddPartInputPort", "InputPort"),
        ("alpha.application.add_part.AddPartUseCase", "InputPort"),
        ("alpha.application.add_part.ThingMissing", "Refusal"),
        ("alpha.application.count_things.TooFewThings", "UseCaseException"),
        ("alpha.application.count_things.TooFewThings", "PortException"),
        ("alpha.adapter.outgoing.memory.InMemoryThingRepository", "Repository"),
        ("alpha.adapter.outgoing.memory.ListPublisher", "DomainEventPublisher"),
        ("beta.api.BetaCatalog", "OpenHostService"),
        ("alpha.domain.endorsement.Endorsements", "DomainGateway"),
        ("beta.events.BetaShipped", "IntegrationEvent"),
    ],
)
def test_the_conforming_fixture_carries_the_roles_its_rules_select_by(name: str, role: str) -> None:
    project = fixture("conforming")
    klass = project.classes[f"fx.{name}"]
    assert project.has(klass, role), f"{name} carries {sorted(project.roles(klass))}"


def test_the_conforming_fixture_places_its_modules() -> None:
    project = fixture("conforming")
    places = {
        m: project.modules[f"fx.{m}"].place
        for m in (
            "alpha.domain.thing",
            "alpha.application.shared",
            "alpha.application.add_part",
            "alpha.adapter.incoming.web.things",
            "alpha.adapter.incoming.event.beta_shipped",
            "alpha.adapter.outgoing.memory",
            "beta.events",
            "sharedkernel.domain.owner",
            "infrastructure",
        )
    }
    assert places["alpha.domain.thing"].layer == "domain"
    assert places["alpha.application.shared"].shared
    assert places["alpha.application.add_part"].feature == ("add_part",)
    assert places["alpha.adapter.incoming.web.things"].sub == "web"
    assert places["alpha.adapter.incoming.event.beta_shipped"].sub == "event"
    assert places["alpha.adapter.outgoing.memory"].layer == "outgoing"
    assert places["beta.events"].layer == "events"
    assert places["sharedkernel.domain.owner"].kernel
    assert places["infrastructure"].layer == "root"
    assert project.declared_contexts() == {"alpha": "alpha", "beta": "beta"}


def test_a_copy_of_the_markers_the_layout_names_counts_as_the_building_blocks() -> None:
    project = fixture("own-markers")
    assert "fx.markers" not in project.modules
    roles = {name.rsplit(".", 1)[-1]: project.roles(k) for name, k in project.classes.items()}
    assert "AggregateRoot" in roles["Thing"]
    assert "Id" in roles["ThingId"] and "Value" in roles["ThingId"]
    assert "Value" in roles["Label"]
    assert not findings(project, "DCA-LAY-007")
    assert not findings(project, "DCA-STR-011")


def test_an_experimental_rule_runs_only_when_switched_on(tmp_path: pathlib.Path) -> None:
    source = FIXTURES / "violations"
    layout = DcaLayout.from_pyproject(source / "pyproject.toml")
    off = Project(DcaLayout(project_root=layout.project_root, base_package="fx"))
    assert run(off, "DCA-PY-004").kind == "experimental"
    assert run(off, "DCA-TAC-003").kind == "ran"
    some = Project(DcaLayout(project_root=layout.project_root, base_package="fx", experimental=("DCA-PY-004",)))
    assert run(some, "DCA-PY-004").findings
    disabled = Project(DcaLayout(project_root=layout.project_root, base_package="fx", disabled=("DCA-TAC-003",)))
    assert run(disabled, "DCA-TAC-003").kind == "disabled"


def test_an_informational_rule_lists_and_never_fails() -> None:
    outcome = run(fixture("violations"), "DCA-ERR-008")
    assert outcome.informational and outcome.findings


def test_the_command_line_fails_with_one_line_per_finding() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "dca_rules", str(FIXTURES / "violations" / "pyproject.toml"), "DCA-TAC-003"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1
    assert done.stdout.splitlines()[1].startswith("[DCA-TAC-003] src/fx/alpha/domain/")
    done = subprocess.run(
        [sys.executable, "-m", "dca_rules", str(FIXTURES / "conforming" / "pyproject.toml")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout
    done = subprocess.run(
        [sys.executable, "-m", "dca_rules", str(FIXTURES / "undeclared" / "pyproject.toml"), "DCA-NAM-007"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1
    assert done.stdout.startswith("[DCA-NAM-007] ") and "nothing selected" in done.stdout


def test_rules_json_knows_every_implemented_rule_and_marks_it() -> None:
    rules = json.loads((pathlib.Path(__file__).parent.parent / "src" / "dca_rules" / "rules.json").read_text())
    flagged = {r["id"] for r in rules["rules"] if r.get("implemented")}
    assert flagged == set(implemented())
    assert set(implemented()) <= set(catalogue())
    assert all(r["maturity"] == "experimental" for r in rules["rules"] if r["id"].startswith("DCA-PY-"))


def test_the_rules_follow_renamed_packages_and_suffixes() -> None:
    """Every package name and suffix the suite places or selects by is renamed in `[tool.dca]`, as Java's DcaLayout
    renames them; the rules follow the configured names and ignore the defaults."""
    project = fixture("renamed")
    found = sorted(
        f"{rule_id} {finding.location}"
        for rule_id in implemented()
        if rule_id not in LISTINGS
        for finding in findings(project, rule_id)
    )
    assert found == [
        "DCA-ADV-013 src/fx/alpha/domain/thing.py:20",
        "DCA-HEX-008 src/fx/alpha/adapter/driving/stray.py:1",
        "DCA-HEX-009 src/fx/alpha/application/common/__init__.py:13",
        "DCA-NAM-001 src/fx/alpha/application/rename_part.py:18",
        "DCA-NAM-003 src/fx/alpha/application/rename_part.py:14",
        "DCA-NAM-004 src/fx/alpha/application/common/__init__.py:13",
        "DCA-TAC-001 src/fx/alpha/domain/thing.py:16",
    ]
    assert all("application.common" in f.message for f in findings(project, "DCA-HEX-009"))
    assert all(f.message.endswith("Service") for f in findings(project, "DCA-NAM-001"))
    # Without the operation container the two use cases sit at two depths.
    flat = Project(dataclasses.replace(project.layout, operation_containers=()))
    assert findings(flat, "DCA-USE-014")


@pytest.mark.parametrize(
    "values",
    [
        {"use_case_suffix": ""},
        {"incoming": "in coming"},
        {"repository_suffix": "1Repo"},
        {"incoming": "adapters", "outgoing": "adapters"},
        {"shared": "ports", "operation_containers": ("ports",)},
    ],
)
def test_a_name_that_is_no_identifier_is_refused(tmp_path: pathlib.Path, values: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        DcaLayout(project_root=tmp_path, base_package="fx", **values)  # type: ignore[arg-type]


def test_integration_events_live_in_a_context_events_package_beside_api() -> None:
    """Java keeps {context}/events beside {context}/api: an integration event in api/events or in the shared kernel is
    reported, one in a context's events package is not."""
    located = {f.location.split(":")[0] for f in findings(fixture("violations"), "DCA-STR-007")}
    assert "src/fx/beta/api/events/__init__.py" in located
    assert "src/fx/sharedkernel/events/__init__.py" in located
    assert not findings(fixture("conforming"), "DCA-STR-007")


def test_the_shared_kernel_has_the_layers_of_a_context() -> None:
    """The kernel's application, outgoing adapters and infrastructure are read as layers; an outgoing adapter of a
    context may reuse the kernel's infrastructure, and the domain gateways may answer asynchronously."""
    project = fixture("conforming")
    places = {m.dotted: m.place for m in project.modules.values()}
    assert places["fx.sharedkernel.application.shared"].layer == "application"
    assert places["fx.sharedkernel.adapter.outgoing"].layer == "outgoing"
    assert places["fx.sharedkernel.infrastructure"].layer == "infrastructure"
    for rule_id in ("DCA-HEX-005", "DCA-ONI-004", "DCA-PY-004", "DCA-HEX-017", "DCA-LAY-008"):
        assert not findings(project, rule_id), rule_id


def _project(root: pathlib.Path, files: dict[str, str]) -> Project:
    """A project written for one test: `files` maps a path below src/fx to its source."""
    (root / "pyproject.toml").write_text('[tool.dca]\nbase-package = "fx"\nexperimental = "all"\n')
    for path, source in {"__init__.py": "", **files}.items():
        target = root / "src" / "fx" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    return Project(DcaLayout.from_pyproject(root / "pyproject.toml"))


def test_a_feature_package_that_re_exports_its_use_case_closes_no_cycle(tmp_path: pathlib.Path) -> None:
    use_case = (
        "from dca_building_blocks import UseCase\n"
        "from fx.alpha.application.things.support import Note\n"
        "class KeepUseCase(UseCase[Note, Note]):\n    pass\n"
    )
    project = _project(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/domain/__init__.py": "",
            "alpha/application/__init__.py": "",
            "alpha/application/things/__init__.py": "from fx.alpha.application.things.keep import KeepUseCase\n",
            "alpha/application/things/keep.py": use_case,
            "alpha/application/things/support.py": "from fx.alpha.application.things import KeepUseCase\nclass Note:\n"
            "    pass\n",
        },
    )
    outcome = run(project, "DCA-CYC-005")
    assert outcome.selected and not outcome.findings, outcome.findings


def test_the_composition_root_alone_is_no_dca_layer(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, {"infrastructure/__init__.py": "x = 1\n"})
    assert findings(project, "DCA-STR-012")


def test_a_project_without_production_code_passes_the_declaration_guards(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, {"__init__.py": '"""Nothing here yet."""\n', "sub/__init__.py": ""})
    for rule_id in ("DCA-STR-011", "DCA-STR-012"):
        outcome = run(project, rule_id)
        assert outcome.kind == "ran" and not outcome.findings, (rule_id, outcome)


def test_the_whole_suite_passes_on_a_project_without_production_code(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, {"__init__.py": '"""Nothing here yet."""\n'})
    (tmp_path / "pyproject.toml").write_text('[tool.dca]\nbase-package = "fx"\n')
    failing = [rule_id for rule_id in implemented() if run(project, rule_id).fails]
    assert not failing
    assert run(project, "DCA-NAM-007").allowed == NO_PRODUCTION_CODE
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_architecture.py").write_text(
        'from dca_rules.testing import architecture_tests\n\ntest_dca = architecture_tests("pyproject.toml")\n'
    )
    for command in (["-m", "dca_rules", "pyproject.toml"], ["-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]):
        done = subprocess.run([sys.executable, *command], cwd=tmp_path, capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stdout + done.stderr


def test_an_empty_selection_still_fails_once_the_project_has_code(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, {"plain.py": "class Plain:\n    pass\n"})
    outcome = run(project, "DCA-NAM-007")
    assert outcome.kind == "empty" and outcome.allowed is None and outcome.fails


def test_one_statement_is_production_code_the_declaration_guards_see(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, {"__init__.py": '"""Something here."""\n\nx = 1\n'})
    assert findings(project, "DCA-STR-011")
    assert findings(project, "DCA-STR-012")


def test_an_implemented_anti_corruption_layer_has_its_translator() -> None:
    found = [f.message for f in findings(fixture("violations"), "DCA-MAP-008")]
    assert any(m.startswith("alpha declares epsilon via events behind an anti-corruption layer") for m in found)
    assert any("uses the api of delta" in m for m in found)


def test_a_bridge_is_exempt_by_itself_not_by_its_module() -> None:
    found = [f.location for f in findings(fixture("violations"), "DCA-HEX-019")]
    assert "src/fx/infrastructure/bridges.py:15" in found
    assert not [location for location in found if location == "src/fx/infrastructure/bridges.py:5"]


def test_transactions_follow_the_configured_apis() -> None:
    layout = DcaLayout.from_pyproject(FIXTURES / "violations" / "pyproject.toml")
    bare = Project(dataclasses.replace(layout, transaction_apis=(), transaction_decorators=()))
    messages = [f.message for f in findings(bare, "DCA-LAY-004")]
    assert messages and all("TransactionBoundary" in m for m in messages)


def test_a_nested_class_is_a_class_of_its_own() -> None:
    project = fixture("violations")
    assert project.has(project.classes["fx.alpha.domain.crate.Shelf.Slot"], "Value")
