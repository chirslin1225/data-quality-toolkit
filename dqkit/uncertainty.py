"""How much should you trust the score?

The headline score is a point estimate computed from every row that was read.
An interval answers the next question: if this file had been captured slightly
differently, how far would the score move?

This module estimates one by **repeated subsampling without replacement**.

Why not a bootstrap over rows with replacement: resampling with replacement
manufactures duplicate rows by construction, which inflates the very defect the
``duplicate`` rule measures, and biases every score upward in burden.

Why ``gap`` is excluded from the interval: a gap is a property of the *capture*,
not of a row. Randomly keeping half the rows leaves roughly the same absolute
number of missing samples while halving the expected count, so a row-level
subsample reports a gap rate about twice the truth. Mixing that into the
interval produces an estimate that does not even bracket the point value —
which is exactly the bug this exclusion exists to prevent. Structural rules are
therefore reported as point values only, and the interval covers the row-level
defects, where subsampling is actually valid.
"""

from __future__ import annotations

import random

from .checks import CHECKS, run_checks
from .score import score

MIN_ROWS = 50

#: Rules whose rate is a property of the whole capture rather than of a row.
STRUCTURAL_RULES = ("gap",)


def _percentile(sorted_values, p):
    if not sorted_values:
        return None
    idx = int(round(p * (len(sorted_values) - 1)))
    return sorted_values[max(0, min(idx, len(sorted_values) - 1))]


def _row_level(findings, excluded):
    return [f for f in findings if f.rule not in excluded]


def estimate_uncertainty(rows, columns, sample_rows=None, iterations=200,
                         costs=None, seed=0, checks=None, params=None,
                         exclude_rules=STRUCTURAL_RULES):
    """Return a dict describing the interval around the score.

    Keys: ``point``, ``low``, ``high``, ``iterations``, ``sample_rows``,
    ``excluded`` (the structural rules left out), ``samples``.

    Returns ``None`` when the table is too small for the interval to mean
    anything (fewer than ``MIN_ROWS`` rows).
    """
    n = len(rows)
    if n < MIN_ROWS:
        return None

    excluded = tuple(exclude_rules or ())
    # Checks whose findings are all excluded are not worth running at all:
    # the gap check alone parses every timestamp, which is the most expensive
    # thing in a subsample.
    sub_checks = [c for c in (checks or list(CHECKS)) if c not in excluded]
    k = sample_rows or max(MIN_ROWS, n // 2)
    k = max(MIN_ROWS // 2, min(k, n - 1))
    iterations = max(20, int(iterations))
    rnd = random.Random(seed)

    def point_of(subset, enabled):
        findings = run_checks(subset, columns, enabled, params)
        return score(_row_level(findings, excluded), costs)

    samples = sorted(point_of(rnd.sample(rows, k), sub_checks)
                     for _ in range(iterations))

    return {
        "point": point_of(rows, sub_checks),
        "low": _percentile(samples, 0.025),
        "high": _percentile(samples, 0.975),
        "iterations": iterations,
        "sample_rows": k,
        "excluded": excluded,
        "samples": samples,
    }
