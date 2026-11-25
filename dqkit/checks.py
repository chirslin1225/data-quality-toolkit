"""Quality checks over a table of rows (one dict per row).

Every check has the same signature::

    check(rows, columns) -> list[Finding]

``rows`` is the output of ``csv.DictReader`` (a list of dicts keyed by column
name) and ``columns`` is the header order. A check must never raise on
malformed data: if it cannot evaluate a column it returns no finding for that
column rather than dying, because a data-quality tool that crashes on bad data
is not much use.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """One defect found in one column (or in the whole table)."""

    rule: str
    column: str
    count: int
    rate: float
    detail: str = ""


def _n(rows) -> int:
    return len(rows) or 1


def check_missing(rows, columns):
    """Empty or whitespace-only cells, counted per column."""
    out = []
    for col in columns:
        n = sum(1 for r in rows if not str(r.get(col, "")).strip())
        if n:
            out.append(Finding("missing", col, n, n / _n(rows)))
    return out


def check_duplicate(rows, columns):
    """Rows that are identical across every column."""
    seen = {}
    for r in rows:
        key = tuple(str(r.get(c, "")).strip() for c in columns)
        seen[key] = seen.get(key, 0) + 1
    n = sum(v - 1 for v in seen.values() if v > 1)
    if not n:
        return []
    return [Finding("duplicate", "*", n, n / _n(rows),
                    detail=f"{sum(1 for v in seen.values() if v > 1)} distinct row(s) repeated")]


def check_constant(rows, columns):
    """Columns that carry a single distinct value (no information)."""
    out = []
    for col in columns:
        values = {str(r.get(col, "")).strip() for r in rows}
        if len(values) == 1 and rows:
            only = next(iter(values))
            out.append(Finding("constant", col, len(rows), 1.0,
                               detail=f"always {only!r}"))
    return out


# ---------------------------------------------------------------------------
# Planned checks.
#
# These are deliberately left unimplemented: each one requires a judgement call
# that belongs to whoever owns the data, not to the tool. Fill them in, register
# them in ``CHECKS`` below, and add a test for each. See README "Roadmap".
# ---------------------------------------------------------------------------

def check_dtype(rows, columns, schema=None):
    """Type conformance against a declared schema.

    TODO: implement. Intended behaviour:
      * ``schema`` maps column name -> a predicate, e.g. ``float`` or a callable.
      * For each column, count the values that fail the predicate.
      * Report the first offending value in ``Finding.detail`` so the reader can
        see *what kind of garbage* it is, not just how much.

    Open question worth documenting in the docstring once you decide: should an
    empty cell count as a dtype failure, or is that already the ``missing``
    check's job? (Counting it twice inflates the score penalty.)
    """
    raise NotImplementedError


def check_gap(rows, columns, time_col=None, expected_interval=None, tolerance=1.5):
    """Irregular sampling in a timestamp column.

    TODO: implement. Intended behaviour:
      * Parse ``time_col`` as ISO-8601, sort it, diff consecutive values.
      * Flag gaps longer than ``expected_interval * tolerance``.
      * ``Finding.count`` should be the number of *missing expected samples*,
        not the number of gaps — three long outages and three single drops are
        very different failures.
      * Ignore rows whose timestamp does not parse, but report how many were
        ignored in ``Finding.detail``.

    This is the check that matters most for multimodal sensor data: a gap in one
    stream silently misaligns every downstream join.
    """
    raise NotImplementedError


def check_outlier(rows, columns, columns_to_check=None, fence=1.5):
    """Robust outlier count per numeric column, using the IQR fence.

    TODO: implement. Intended behaviour:
      * Parse values as float; skip non-numeric ones.
      * Lower = Q1 - fence * IQR, upper = Q3 + fence * IQR.
      * Report the count outside the fence plus the fence bounds in ``detail``.
      * Note in the docstring why IQR is preferred over mean ± k·std here
        (the std is itself dragged around by the outliers you are trying to find).
    """
    raise NotImplementedError


CHECKS = {
    "missing": check_missing,
    "duplicate": check_duplicate,
    "constant": check_constant,
}

PLANNED = {
    "dtype": check_dtype,
    "gap": check_gap,
    "outlier": check_outlier,
}


def run_checks(rows, columns, enabled=None):
    """Run the requested checks (default: all implemented ones) and return findings."""
    names = enabled or list(CHECKS)
    findings = []
    for name in names:
        fn = CHECKS.get(name)
        if fn is None:
            raise ValueError(f"unknown or unimplemented check: {name!r} "
                             f"(implemented: {sorted(CHECKS)})")
        findings.extend(fn(rows, columns))
    return findings
