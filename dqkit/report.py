"""Markdown report rendering."""

from __future__ import annotations

import datetime as _dt

from .score import DEFAULT_COSTS, burdens, interpret, score


def _fmt_rate(rate):
    return f"{rate * 100:.2f}%"


def render(findings, rows, columns, source="<stdin>", costs=None,
           generated_at=None, uncertainty=None):
    """Return a Markdown report for the given findings.

    ``uncertainty`` is the dict returned by
    :func:`dqkit.uncertainty.estimate_uncertainty`; when present the score line
    gains a 95% interval.
    """
    value = score(findings, costs)
    stamp = (generated_at or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Data Quality Report — `{source}`",
        "",
        f"Rows: {rows:,}   Columns: {len(columns)}   Generated: {stamp}",
        "",
        f"## Score: {value:.1f} / 100",
        "",
        f"_{interpret(value)}_",
        "",
    ]

    if uncertainty:
        note = ""
        if uncertainty.get("excluded"):
            note = (f" `{'`, `'.join(uncertainty['excluded'])}` is a property of the "
                    f"capture rather than of a row, so it is excluded here and "
                    f"reported as a point value in the table.")
        lines += [
            f"Row-level score: **{uncertainty['point']:.1f} / 100**, "
            f"95% interval **{uncertainty['low']:.1f} – {uncertainty['high']:.1f}** "
            f"({uncertainty['iterations']} subsamples of "
            f"{uncertainty['sample_rows']:,} rows, without replacement).{note}",
            "",
        ]

    if not findings:
        lines += ["No defects found by the enabled checks.", ""]
        return "\n".join(lines)

    eff_costs = {**DEFAULT_COSTS, **(costs or {})}
    pairs = burdens(findings, costs)
    lines += [
        "| Rule | Column | Count | Rate | Cost | Burden |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for f, b in pairs:
        lines.append(
            f"| {f.rule} | `{f.column}` | {f.count:,} | {_fmt_rate(f.rate)} "
            f"| {eff_costs.get(f.rule, 1.0):.1f} | {b:.2f} |"
        )
    lines.append("")

    details = [(f, b) for f, b in pairs if f.detail]
    if details:
        lines += ["### Notes", ""]
        for f, _ in details:
            lines.append(f"- `{f.column}` ({f.rule}): {f.detail}")
        lines.append("")

    lines += [
        "### How to read this",
        "",
        "Burden = defect rate × error cost. Rules are listed most expensive first, "
        "so the top row is where repair effort pays off most.",
        "",
        f"Score = 100 × exp(−Σ burden) = {value:.1f}.",
        "",
    ]
    return "\n".join(lines)
