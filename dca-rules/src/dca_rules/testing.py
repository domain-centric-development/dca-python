"""The rule suite as pytest tests: one parametrized test, one case per implemented rule id."""

from __future__ import annotations

import functools
import pathlib
from collections.abc import Callable

import pytest

from dca_rules import implemented, report, run
from dca_rules.layout import DcaLayout
from dca_rules.model import Project


def architecture_tests(pyproject: str | pathlib.Path = "pyproject.toml") -> Callable[[str], None]:
    """A test function parametrized over every implemented rule. A finding fails its case; an informational
    rule prints its list; an experimental rule not switched on in `[tool.dca] experimental` is skipped."""
    path = pathlib.Path(pyproject)

    @functools.cache
    def project() -> Project:
        found = Project(DcaLayout.from_pyproject(path))
        if found.problems:
            raise AssertionError("files the suite could not read:\n" + "\n".join(found.problems))
        return found

    @pytest.mark.parametrize("rule_id", implemented())
    def test_dca(rule_id: str) -> None:
        outcome = run(project(), rule_id)
        if outcome.kind != "ran":
            pytest.skip(f"[{rule_id}] {outcome.kind}: switch it on in [tool.dca] experimental")
        if outcome.informational:
            print(report(rule_id, outcome))
        elif outcome.findings:
            pytest.fail(report(rule_id, outcome), pytrace=False)

    return test_dca
