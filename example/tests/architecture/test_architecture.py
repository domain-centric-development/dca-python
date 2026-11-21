"""The DCA rule suite over the library: one case per rule id."""

from dca_rules.testing import architecture_tests

test_dca = architecture_tests("pyproject.toml")
