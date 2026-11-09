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
    """A test function parametrized over every implemented rule. A finding fails its case; so does a rule that
    selected nothing, unless `[tool.dca] allow-empty` names it with a reason - then it passes and prints the reason.
    An informational rule prints its list and never fails; an experimental rule not switched on in
    `[tool.dca] experimental` is skipped."""
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
        if outcome.kind == "experimental":
            pytest.skip(f"[{rule_id}] experimental: switch it on in [tool.dca] experimental")
        if outcome.kind == "disabled":
            pytest.skip(f"[{rule_id}] disabled in [tool.dca] disabled")
        if outcome.fails:
            pytest.fail(report(rule_id, outcome), pytrace=False)
        if outcome.informational or outcome.kind == "empty" or outcome.allowed is not None:
            print(report(rule_id, outcome))

    return test_dca
