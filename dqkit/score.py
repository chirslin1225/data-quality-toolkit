"""Cost-weighted scoring.

The point of this module is that not all defects cost the same. A missing
timestamp breaks a join; a missing marketing tag is cosmetic. Counting both as
"one missing value" hides the thing you actually care about.

burden  = defect_rate x error_cost
score   = 100 * exp(-sum(burden))

``error_cost`` is a relative weight in arbitrary units, not money. It encodes
the ordering of your pains, which is the only part a tool cannot know.
"""

from __future__ import annotations

import math

#: Relative cost of one defect, per unit of defect rate.
#: Override with ``--costs my_costs.json`` — a partial file is merged over these.
#:
#: ``constant`` is deliberately cheap. A column with no variance is usually
#: metadata (a fixed device id, a fixed firmware version) and the repair is to
#: drop the column, not to rescue rows. Because that finding's rate is always
#: 1.0, giving it a high cost would let one harmless column bury every real
#: defect. This is exactly the kind of judgement the tool cannot make for you —
#: see README, "How the score works".
DEFAULT_COSTS = {
    "missing": 3.0,
    "duplicate": 1.0,
    "constant": 0.1,
    "dtype": 2.0,
    "gap": 4.0,
    "outlier": 1.0,
}


def burdens(findings, costs=None):
    """Return ``[(finding, burden), ...]`` sorted by descending burden."""
    costs = {**DEFAULT_COSTS, **(costs or {})}
    pairs = []
    for f in findings:
        cost = costs.get(f.rule, 1.0)
        pairs.append((f, f.rate * cost))
    pairs.sort(key=lambda p: p[1], reverse=True)
    return pairs


def total_burden(findings, costs=None):
    return sum(b for _, b in burdens(findings, costs))


def score(findings, costs=None):
    """0-100. 100 means no defect among the implemented checks."""
    return 100.0 * math.exp(-total_burden(findings, costs))


def interpret(value):
    """One-line reading of a score, for the report header."""
    if value >= 95:
        return "clean enough to use as-is"
    if value >= 80:
        return "usable, but fix the highest-burden rows first"
    if value >= 60:
        return "needs targeted repair before it feeds a model"
    if value >= 35:
        return "risky: defects are concentrated in high-cost rules"
    return "do not train on this without repair"


# ---------------------------------------------------------------------------
# Planned.
# ---------------------------------------------------------------------------

def estimate_uncertainty(findings, n_rows, sample_rows=None, iterations=200,
                         costs=None):
    """Confidence interval for :func:`score` when the file is too big to scan fully.

    TODO: implement. Intended behaviour:
      * Draw ``iterations`` bootstrap samples of ``sample_rows`` rows each
        (default: something like 10% of the file, floor 1000).
      * Recompute the score for each sample.
      * Return ``(point_estimate, lower_p05, upper_p95)``.

    The hard part is not the bootstrap, it is deciding what "uncertain" means
    here: sampling error in the rate estimate, or the possibility that the
    defect mechanism is *not* independent across rows (it rarely is — a broken
    sensor fails in runs, not at random). A row-level bootstrap assumes
    independence and will understate the true spread. If you implement this,
    say so in the README, and consider a block bootstrap keyed on time or device.
    """
    raise NotImplementedError
