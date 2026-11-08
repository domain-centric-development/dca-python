"""`python -m dca_rules [pyproject.toml] [RULE-ID ...]`: every finding, one line each, and every rule that selected
nothing; exit 1 when a rule fails - a finding, or an empty selection `[tool.dca] allow-empty` does not name."""

from __future__ import annotations

import sys

from dca_rules import implemented, report, run
from dca_rules.layout import DcaLayout
from dca_rules.model import Project


def main(argv: list[str]) -> int:
    pyproject = next((a for a in argv if a.endswith(".toml")), "pyproject.toml")
    wanted = [a for a in argv if a.startswith("DCA-")] or implemented()
    project = Project(DcaLayout.from_pyproject(pyproject))
    for problem in project.problems:
        print(problem, file=sys.stderr)
    failed = 0
    for rule_id in wanted:
        outcome = run(project, rule_id)
        if outcome.findings or outcome.kind == "empty":
            print(report(rule_id, outcome))
        failed += 1 if outcome.fails else 0
    return 1 if failed or project.problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
