"""Tests for the implemented checks and the scoring formula.

Run with:  python -m unittest discover -s tests -v
"""

import unittest

from dqkit.checks import check_constant, check_duplicate, check_missing, run_checks
from dqkit.score import DEFAULT_COSTS, burdens, score


def table():
    return [
        {"a": "1", "b": "x"},
        {"a": "", "b": "x"},
        {"a": "3", "b": " "},
        {"a": "3", "b": " "},   # exact duplicate of the previous row
    ]


COLS = ["a", "b"]


class TestMissing(unittest.TestCase):
    def test_counts_blank_and_whitespace(self):
        f = {x.column: x for x in check_missing(table(), COLS)}
        self.assertEqual(f["a"].count, 1)
        self.assertEqual(f["b"].count, 2)          # " " is missing too
        self.assertAlmostEqual(f["a"].rate, 0.25)

    def test_no_finding_when_clean(self):
        rows = [{"a": "1"}, {"a": "2"}]
        self.assertEqual(check_missing(rows, ["a"]), [])


class TestDuplicate(unittest.TestCase):
    def test_counts_extra_copies_not_rows(self):
        findings = check_duplicate(table(), COLS)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].count, 1)     # one extra copy, not two rows
        self.assertEqual(findings[0].column, "*")

    def test_clean_table(self):
        rows = [{"a": "1"}, {"a": "2"}]
        self.assertEqual(check_duplicate(rows, ["a"]), [])


class TestConstant(unittest.TestCase):
    def test_detects_single_value_column(self):
        rows = [{"a": "1", "b": "same"}, {"a": "2", "b": "same"}]
        f = {x.column: x for x in check_constant(rows, ["a", "b"])}
        self.assertEqual(list(f), ["b"])
        self.assertIn("same", f["b"].detail)


class TestScore(unittest.TestCase):
    def test_perfect_score_has_no_findings(self):
        self.assertAlmostEqual(score([]), 100.0)

    def test_score_decreases_with_more_defects(self):
        light = check_missing([{"a": ""}] + [{"a": "x"}] * 9, ["a"])
        heavy = check_missing([{"a": ""}] * 9 + [{"a": "x"}], ["a"])
        self.assertGreater(score(light), score(heavy))

    def test_cost_ordering_matters(self):
        finding = check_missing([{"a": ""}] + [{"a": "x"}] * 9, ["a"])
        cheap = score(finding, {"missing": 0.1})
        dear = score(finding, {"missing": 10.0})
        self.assertGreater(cheap, dear)

    def test_burdens_sorted_descending(self):
        findings = check_missing([{"a": ""}, {"b": ""}, {"a": "x", "b": "x"}], ["a", "b"])
        values = [b for _, b in burdens(findings)]
        self.assertEqual(values, sorted(values, reverse=True))


class TestRunner(unittest.TestCase):
    def test_unknown_check_raises(self):
        with self.assertRaises(ValueError):
            run_checks([], [], ["nope"])

    def test_default_runs_all_implemented(self):
        findings = run_checks(table(), COLS)
        self.assertTrue(any(f.rule == "missing" for f in findings))

    def test_default_costs_cover_every_implemented_rule(self):
        for rule in ("missing", "duplicate", "constant"):
            self.assertIn(rule, DEFAULT_COSTS)


if __name__ == "__main__":
    unittest.main()
