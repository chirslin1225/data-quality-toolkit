"""Tests for the checks, the scoring formula and the uncertainty interval.

Run with:  python -m unittest discover -s tests -v
"""

import datetime as dt
import unittest

from dqkit.checks import (check_constant, check_dtype, check_duplicate, check_gap,
                          check_missing, check_outlier, run_checks)
from dqkit.score import DEFAULT_COSTS, burdens, score
from dqkit.uncertainty import estimate_uncertainty


def table():
    return [
        {"a": "1", "b": "x"},
        {"a": "", "b": "x"},
        {"a": "3", "b": " "},
        {"a": "3", "b": " "},   # exact duplicate of the previous row
    ]


COLS = ["a", "b"]


def series(n=400, step_ms=20, skip_at=(), junk_at=(), seed=1):
    """A regular time series with optional gaps and unparseable stamps."""
    out = []
    t = dt.datetime(2026, 1, 1, 0, 0, 0)
    step = dt.timedelta(milliseconds=step_ms)
    for i in range(n):
        if i in skip_at:
            t += step * 300
        out.append({"timestamp": t.isoformat(timespec="milliseconds"),
                    "v": f"{i % 17}"})
        t += step
    for i in junk_at:
        out[i]["timestamp"] = "n/a"
    return out


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


class TestDtype(unittest.TestCase):
    def test_infers_numeric_column_and_flags_junk(self):
        rows = [{"v": str(i)} for i in range(20)] + [{"v": "ERR"}]
        findings = check_dtype(rows, ["v"])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].column, "v")
        self.assertEqual(findings[0].count, 1)
        self.assertIn("ERR", findings[0].detail)

    def test_blank_is_not_a_type_error(self):
        rows = [{"v": "1.0"}, {"v": "2.0"}, {"v": ""}]
        self.assertEqual(check_dtype(rows, ["v"]), [])

    def test_declared_schema_wins(self):
        rows = [{"v": "1"}, {"v": "2"}, {"v": "x"}]
        findings = check_dtype(rows, ["v"], schema={"v": "float"})
        self.assertEqual(findings[0].count, 1)

    def test_free_text_column_is_not_typed(self):
        rows = [{"v": "alpha"}, {"v": "beta"}, {"v": "gamma"}]
        self.assertEqual(check_dtype(rows, ["v"]), [])


class TestGap(unittest.TestCase):
    def test_counts_missing_samples_not_gaps(self):
        rows = series(n=400, skip_at=(100, 200))
        findings = check_gap(rows, ["timestamp"])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].column, "timestamp")
        # two outages, each dropping ~300 samples of 20 ms
        self.assertGreater(findings[0].count, 500)
        self.assertIn("gap", findings[0].rule)

    def test_regular_series_has_no_gap(self):
        self.assertEqual(check_gap(series(n=200), ["timestamp"]), [])

    def test_explicit_interval_is_respected(self):
        rows = series(n=300)
        findings = check_gap(rows, ["timestamp"], expected_interval=0.001, tolerance=2.0)
        self.assertEqual(len(findings), 1)

    def test_no_timestamp_column_is_silent(self):
        rows = [{"a": "1"}, {"a": "2"}, {"a": "3"}]
        self.assertEqual(check_gap(rows, ["a"]), [])

    def test_unparseable_stamps_do_not_crash(self):
        rows = series(n=300, junk_at=(5, 6))
        check_gap(rows, ["timestamp"])   # must not raise


class TestOutlier(unittest.TestCase):
    def test_flags_injected_extremes(self):
        rows = [{"v": str(i % 20)} for i in range(200)]
        rows += [{"v": "500"}, {"v": "-500"}]
        findings = check_outlier(rows, ["v"])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].count, 2)

    def test_uniform_column_has_no_outliers(self):
        rows = [{"v": str(i % 50)} for i in range(300)]
        self.assertEqual(check_outlier(rows, ["v"]), [])

    def test_skips_non_numeric_columns(self):
        rows = [{"v": f"x{i}"} for i in range(50)]
        self.assertEqual(check_outlier(rows, ["v"]), [])


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


class TestUncertainty(unittest.TestCase):
    def test_small_table_returns_none(self):
        rows = [{"a": "1"} for _ in range(10)]
        self.assertIsNone(estimate_uncertainty(rows, ["a"]))

    def test_interval_brackets_the_point_estimate(self):
        rows = [{"a": str(i), "b": "" if i % 10 == 0 else "x"} for i in range(400)]
        u = estimate_uncertainty(rows, ["a", "b"], iterations=60, seed=3)
        self.assertIsNotNone(u)
        self.assertLessEqual(u["low"], u["point"] + 1e-9)
        self.assertGreaterEqual(u["high"], u["point"] - 1e-9)
        self.assertEqual(u["iterations"], 60)


class TestRunner(unittest.TestCase):
    def test_unknown_check_raises(self):
        with self.assertRaises(ValueError):
            run_checks([], [], ["nope"])

    def test_default_runs_all_implemented(self):
        findings = run_checks(table(), COLS)
        self.assertTrue(any(f.rule == "missing" for f in findings))

    def test_params_are_forwarded(self):
        rows = series(n=300)
        findings = run_checks(rows, ["timestamp"], ["gap"],
                              {"gap": {"expected_interval": 0.001, "tolerance": 2.0}})
        self.assertEqual(len(findings), 1)

    def test_default_costs_cover_every_implemented_rule(self):
        for rule in ("missing", "duplicate", "constant", "dtype", "gap", "outlier"):
            self.assertIn(rule, DEFAULT_COSTS)


if __name__ == "__main__":
    unittest.main()
