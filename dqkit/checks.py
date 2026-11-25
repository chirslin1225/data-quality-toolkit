"""Quality checks over a table of rows (one dict per row).

Every check has the same signature::

    check(rows, columns, **params) -> list[Finding]

``rows`` is the output of ``csv.DictReader`` (a list of dicts keyed by column
name) and ``columns`` is the header order. A check must never raise on
malformed data: if it cannot evaluate a column it returns no finding for that
column rather than dying, because a data-quality tool that crashes on bad data
is not much use.
"""

from __future__ import annotations

import datetime as _dt
import statistics
from dataclasses import dataclass

#: How many values to look at when *guessing* a column's type. Type inference is
#: only ever a heuristic, and looking at every value of every column is what made
#: a 200-subsample bootstrap take minutes instead of seconds.
SAMPLE = 200


@dataclass(frozen=True)
class Finding:
    """One defect found in one column (or in the whole table)."""

    rule: str
    column: str
    count: int
    rate: float
    detail: str = ""


# ---------------------------------------------------------------------------
# value parsing helpers
# ---------------------------------------------------------------------------

def _n(rows) -> int:
    return len(rows) or 1


def _raw(value) -> str:
    return str(value if value is not None else "").strip()


def _is_empty(value) -> bool:
    return not _raw(value)


def _to_float(value):
    """Return a float, or None when the value is not a number."""
    try:
        return float(_raw(value))
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(_raw(value))
    except (TypeError, ValueError):
        f = _to_float(value)
        return int(f) if f is not None and float(f).is_integer() else None


def _to_datetime(value):
    """Parse an ISO-8601-ish timestamp. Naive datetimes only.

    ``fromisoformat`` covers ``2026-03-01T08:00:00.000`` and friends on 3.7+;
    the explicit formats cover the common space- and slash-separated variants.
    """
    s = _raw(value)
    if not s:
        return None
    try:
        d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d",
                "%d/%m/%Y", "%Y%m%d"):
        try:
            return _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# implemented checks
# ---------------------------------------------------------------------------

def check_missing(rows, columns, **_):
    """Empty or whitespace-only cells, counted per column."""
    out = []
    for col in columns:
        n = sum(1 for r in rows if _is_empty(r.get(col)))
        if n:
            out.append(Finding("missing", col, n, n / _n(rows)))
    return out


def check_duplicate(rows, columns, **_):
    """Rows that are identical across every column."""
    seen = {}
    for r in rows:
        key = tuple(_raw(r.get(c)) for c in columns)
        seen[key] = seen.get(key, 0) + 1
    n = sum(v - 1 for v in seen.values() if v > 1)
    if not n:
        return []
    return [Finding("duplicate", "*", n, n / _n(rows),
                    detail=f"{sum(1 for v in seen.values() if v > 1)} distinct row(s) repeated")]


def check_constant(rows, columns, **_):
    """Columns that carry a single distinct value (no information)."""
    out = []
    for col in columns:
        values = {_raw(r.get(col)) for r in rows}
        if len(values) == 1 and rows:
            only = next(iter(values))
            out.append(Finding("constant", col, len(rows), 1.0, detail=f"always {only!r}"))
    return out


def _infer_predicate(values):
    """Guess what a column is supposed to be, from the values that are present.

    Returns a predicate, or None when the column gives no usable signal (a
    free-text column is not "wrong", it is just not typed).

    The ratio is measured on at most ``SAMPLE`` values: inferring the type is a
    cheap approximation anyway, and scanning every value of every column on
    every run is what makes a bootstrap over 200 subsamples feel slow.
    """
    if not values:
        return None
    probe = values[:SAMPLE]
    numeric = sum(1 for v in probe if _to_float(v) is not None)
    if numeric / len(probe) >= 0.9:
        return lambda v: _to_float(v) is not None
    temporal = sum(1 for v in probe if _to_datetime(v) is not None)
    if temporal / len(probe) >= 0.9:
        return lambda v: _to_datetime(v) is not None
    return None


def check_dtype(rows, columns, schema=None, **_):
    """Type conformance, against a declared schema or an inferred one.

    ``schema`` maps a column name to ``"float"``, ``"int"``, ``"date"``,
    ``"str"`` or a predicate. Columns with no entry are inferred: if at least
    90% of the present values parse as a number (or as a date) the column is
    treated as that type and the remaining values are reported.

    Empty cells are *not* counted here — that is the ``missing`` check's job.
    Counting a blank as both a missing value and a type failure would penalise
    it twice and make the two rules impossible to compare.
    """
    out = []
    for col in columns:
        values = [_raw(r.get(col)) for r in rows]
        present = [v for v in values if v]
        if not present:
            continue
        declared = (schema or {}).get(col)
        if declared == "str":
            continue
        if declared == "float":
            bad = [v for v in present if _to_float(v) is None]
        elif declared == "int":
            bad = [v for v in present if _to_int(v) is None]
        elif declared == "date":
            bad = [v for v in present if _to_datetime(v) is None]
        elif callable(declared):
            bad = [v for v in present if not declared(v)]
        else:
            predicate = _infer_predicate(present)
            bad = [v for v in present if not predicate(v)] if predicate else []
        if bad:
            expected = declared if isinstance(declared, str) else "inferred type"
            out.append(Finding("dtype", col, len(bad), len(bad) / _n(rows),
                               detail=f"e.g. {bad[0]!r}; expected {expected}"))
    return out


def _guess_time_column(rows, columns, probe=SAMPLE):
    """Pick the column to treat as a timestamp.

    Detection looks at at most ``probe`` rows. A column that parses as a
    timestamp for the first 200 rows and not for the rest would be strange
    enough that ``check_dtype`` will have flagged it anyway.
    """
    sample = rows[:probe]
    for col in columns:
        name = col.lower()
        if any(k in name for k in ("timestamp", "datetime", "time", "date", "_ts")):
            present = [r for r in sample if _raw(r.get(col))]
            parsed = sum(1 for r in present if _to_datetime(r.get(col)) is not None)
            if present and parsed / len(present) >= 0.9:
                return col
    for col in columns:
        present = [r for r in sample if _raw(r.get(col))]
        parsed = sum(1 for r in present if _to_datetime(r.get(col)) is not None)
        if present and parsed / len(present) >= 0.9:
            return col
    return None


def check_gap(rows, columns, time_col=None, expected_interval=None, tolerance=1.5, **_):
    """Missing samples in a regularly-sampled timestamp column.

    Counts the number of *expected-but-absent samples*, not the number of
    gaps: three 10-second outages and three single dropped samples are the same
    "three gaps" and very different problems.

    ``expected_interval`` is in seconds; when omitted it is taken as the median
    positive difference between consecutive timestamps. A difference longer
    than ``expected_interval * tolerance`` counts as a gap.

    Unparseable timestamps are excluded from the analysis (they are reported by
    ``check_dtype`` instead). A single outlier timestamp can create a fake pair
    of gaps, which is why tolerance defaults well above 1.0.
    """
    col = time_col or _guess_time_column(rows, columns)
    if col is None:
        return []

    parsed = []
    for r in rows:
        d = _to_datetime(r.get(col))
        if d is not None:
            parsed.append(d)
    if len(parsed) < 3:
        return []
    parsed.sort()

    diffs = [(b - a).total_seconds() for a, b in zip(parsed, parsed[1:])]
    positive = [d for d in diffs if d > 0]
    if not positive:
        return []

    interval = expected_interval if expected_interval is not None else statistics.median(positive)
    if not interval or interval <= 0:
        return []
    threshold = interval * tolerance

    gaps = 0
    missing = 0
    for d in positive:
        if d > threshold:
            gaps += 1
            missing += max(0, int(round(d / interval)) - 1)
    if not missing:
        return []

    expected_total = len(parsed) + missing
    detail = (f"{gaps} gap(s) over {threshold:.3f}s; "
              f"expected interval {interval:.3f}s")
    return [Finding("gap", col, missing, missing / expected_total, detail=detail)]


def check_outlier(rows, columns, columns_to_check=None, fence=1.5, **_):
    """Robust outliers per numeric column, using the IQR fence.

    Bounds are ``Q1 - fence*IQR`` and ``Q3 + fence*IQR``. IQR is used instead
    of mean +/- k*std because the standard deviation is itself dragged around
    by the very outliers being looked for; on a column with a handful of large
    values a mean-based rule can hide them entirely.

    Non-numeric cells are skipped rather than counted (again, ``check_dtype``
    owns those), and columns where fewer than 90% of present values parse as
    numbers are not treated as numeric at all.
    """
    out = []
    targets = columns_to_check or columns
    for col in targets:
        values = []
        present = 0
        for r in rows:
            raw = _raw(r.get(col))
            if not raw:
                continue
            present += 1
            f = _to_float(raw)
            if f is not None:
                values.append(f)
        if present < 8 or len(values) < 8 or len(values) / present < 0.9:
            continue
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
        iqr = q3 - q1
        if iqr <= 0:
            continue
        low, high = q1 - fence * iqr, q3 + fence * iqr
        bad = sum(1 for v in values if v < low or v > high)
        if bad:
            out.append(Finding("outlier", col, bad, bad / _n(rows),
                               detail=f"outside [{low:.3f}, {high:.3f}]") )
    return out


CHECKS = {
    "missing": check_missing,
    "duplicate": check_duplicate,
    "constant": check_constant,
    "dtype": check_dtype,
    "gap": check_gap,
    "outlier": check_outlier,
}

#: Rules that a check can emit but that are not run by default, kept here so the
#: CLI can list them.
PLANNED = {}


def run_checks(rows, columns, enabled=None, params=None):
    """Run the requested checks (default: all of them) and return findings.

    ``params`` maps a check name to the keyword arguments for that check, e.g.
    ``{"gap": {"expected_interval": 0.02}}``.
    """
    names = enabled or list(CHECKS)
    params = params or {}
    findings = []
    for name in names:
        fn = CHECKS.get(name)
        if fn is None:
            raise ValueError(f"unknown check: {name!r} (implemented: {sorted(CHECKS)})")
        findings.extend(fn(rows, columns, **params.get(name, {})))
    return findings
