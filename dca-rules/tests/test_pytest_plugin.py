"""`architecture_tests` turns the suite into one pytest case per rule id."""

from __future__ import annotations

import pathlib
import subprocess
import sys

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"


def pytest_on(tmp_path: pathlib.Path, fixture: str | pathlib.Path) -> subprocess.CompletedProcess[str]:
    test = tmp_path / "test_architecture.py"
    pyproject = (fixture if isinstance(fixture, pathlib.Path) else FIXTURES / fixture / "pyproject.toml").as_posix()
    test.write_text(
        f"from dca_rules.testing import architecture_tests\n\ntest_dca = architecture_tests({pyproject!r})\n"
    )
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )


def test_a_conforming_project_passes_every_rule(tmp_path: pathlib.Path) -> None:
    done = pytest_on(tmp_path, "conforming")
    assert done.returncode == 0, done.stdout
    assert " passed" in done.stdout


def test_a_violation_fails_the_case_named_after_its_rule(tmp_path: pathlib.Path) -> None:
    done = pytest_on(tmp_path, "violations")
    assert done.returncode == 1
    assert "test_dca[DCA-TAC-003]" in done.stdout
    assert "[DCA-TAC-003] src/fx/alpha/domain/model.py:" in done.stdout


def test_a_rule_that_selects_nothing_fails_unless_allowed(tmp_path: pathlib.Path) -> None:
    source = (FIXTURES / "conforming" / "src").as_posix()
    bare = tmp_path / "pyproject.toml"
    bare.write_text(f'[tool.dca]\nbase-package = "fx"\nsource-root = "{source}"\nexperimental = "all"\n')
    done = pytest_on(tmp_path, bare)
    assert done.returncode == 1
    assert "test_dca[DCA-NAM-007]" in done.stdout
    assert (
        "[DCA-NAM-007] DTOs must reside in the adapter layer, not in domain or application: nothing selected"
        in done.stdout
    )
