"""Every implemented rule fires on the line a fixture marks with its id, none fires on the conforming fixture, and the
roles the rules select by are found.

`fixtures/violations` holds at least one violation per rule, its line marked `# DCA-XXX-nnn`; `fixtures/undeclared`
is a project without a context or a layer; `fixtures/conforming` follows every rule. None is ever run.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest
from dca_rules import Finding, catalogue, implemented, run
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
    assert outcome.kind == "ran", f"{rule_id} did not run: {outcome.kind}"
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
        ("beta.api.events.BetaShipped", "IntegrationEvent"),
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
            "beta.api.events",
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
    assert (places["beta.api.events"].layer, places["beta.api.events"].sub) == ("api", "events")
    assert places["sharedkernel.domain.owner"].kernel
    assert places["infrastructure"].layer == "root"
    assert project.declared_contexts() == {"alpha": "alpha", "beta": "beta"}


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
    assert done.stdout.splitlines()[1].startswith("[DCA-TAC-003] src/fx/alpha/domain/model.py:")
    done = subprocess.run(
        [sys.executable, "-m", "dca_rules", str(FIXTURES / "conforming" / "pyproject.toml")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout


def test_rules_json_knows_every_implemented_rule_and_marks_it() -> None:
    rules = json.loads((pathlib.Path(__file__).parent.parent / "src" / "dca_rules" / "rules.json").read_text())
    flagged = {r["id"] for r in rules["rules"] if r.get("implemented")}
    assert flagged == set(implemented())
    assert set(implemented()) <= set(catalogue())
    assert all(r["maturity"] == "experimental" for r in rules["rules"] if r["id"].startswith("DCA-PY-"))
