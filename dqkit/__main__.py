"""Command-line entry point: ``python -m dqkit data.csv``."""

from __future__ import annotations

import argparse
import csv
import json
import sys

from . import checks as _checks
from .report import render
from .uncertainty import estimate_uncertainty


def load_table(path):
    """Read a CSV into ``(rows, columns)``. A UTF-8 BOM is tolerated."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return rows, columns


def _build_params(args):
    """Collect the per-check keyword arguments that were actually given."""
    params = {}
    gap = {}
    if args.time_col:
        gap["time_col"] = args.time_col
    if args.interval is not None:
        gap["expected_interval"] = args.interval
    if args.tolerance is not None:
        gap["tolerance"] = args.tolerance
    if gap:
        params["gap"] = gap
    if args.fence is not None:
        params["outlier"] = {"fence": args.fence}
    if args.schema:
        with open(args.schema, encoding="utf-8") as fh:
            params["dtype"] = {"schema": json.load(fh)}
    return params


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dqkit",
        description="Score tabular data quality with cost-weighted defect rules.",
    )
    parser.add_argument("csv", help="path to a .csv file")
    parser.add_argument("--checks", default=",".join(_checks.CHECKS),
                        help=f"comma-separated checks to run "
                             f"(default: {','.join(_checks.CHECKS)})")
    parser.add_argument("--costs", help="JSON file with {rule: cost} overrides")
    parser.add_argument("--ignore", default="",
                        help="comma-separated columns to exclude from the checks")
    parser.add_argument("--out", help="write the report here instead of stdout")
    parser.add_argument("--list-checks", action="store_true",
                        help="show the available checks, then exit")

    tuning = parser.add_argument_group("check tuning")
    tuning.add_argument("--time-col", help="column to treat as the timestamp (default: auto)")
    tuning.add_argument("--interval", type=float,
                        help="expected sampling interval in seconds (default: median gap)")
    tuning.add_argument("--tolerance", type=float,
                        help="a diff over interval*tolerance counts as a gap (default 1.5)")
    tuning.add_argument("--fence", type=float,
                        help="IQR fence multiplier for outliers (default 1.5)")
    tuning.add_argument("--schema", help="JSON file mapping column -> float|int|date|str")

    parser.add_argument("--bootstrap", type=int, default=0, metavar="N",
                        help="report a 95%% interval from N subsamples (0 = off; try 200)")
    args = parser.parse_args(argv)

    if args.list_checks:
        print("available:", ", ".join(sorted(_checks.CHECKS)))
        return 0

    costs = None
    if args.costs:
        with open(args.costs, encoding="utf-8") as fh:
            costs = json.load(fh)

    rows, columns = load_table(args.csv)
    ignored = {c.strip() for c in args.ignore.split(",") if c.strip()}
    columns = [c for c in columns if c not in ignored]
    enabled = [c.strip() for c in args.checks.split(",") if c.strip()]
    params = _build_params(args)

    findings = _checks.run_checks(rows, columns, enabled, params)
    uncertainty = None
    if args.bootstrap:
        uncertainty = estimate_uncertainty(rows, columns, iterations=args.bootstrap,
                                           costs=costs, checks=enabled, params=params)
        if uncertainty is None:
            print(f"note: fewer than 50 rows, no interval for --bootstrap "
                  f"{args.bootstrap}", file=sys.stderr)

    text = render(findings, len(rows), columns, source=args.csv, costs=costs,
                  uncertainty=uncertainty)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"report written to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
