"""Command-line entry point: ``python -m dqkit data.csv``."""

from __future__ import annotations

import argparse
import csv
import json
import sys

from . import checks as _checks
from .report import render


def load_table(path):
    """Read a CSV into ``(rows, columns)``. A UTF-8 BOM is tolerated."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return rows, columns


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dqkit",
        description="Score tabular data quality with cost-weighted defect rules.",
    )
    parser.add_argument("csv", help="path to a .csv file")
    parser.add_argument("--checks", default=",".join(_checks.CHECKS),
                        help=f"comma-separated checks to run (default: {','.join(_checks.CHECKS)})")
    parser.add_argument("--costs", help="JSON file with {rule: cost} overrides")
    parser.add_argument("--ignore", default="",
                        help="comma-separated columns to exclude from the checks")
    parser.add_argument("--out", help="write the report here instead of stdout")
    parser.add_argument("--list-checks", action="store_true",
                        help="show implemented and planned checks, then exit")
    args = parser.parse_args(argv)

    if args.list_checks:
        print("implemented:", ", ".join(sorted(_checks.CHECKS)))
        print("planned    :", ", ".join(sorted(_checks.PLANNED)))
        return 0

    costs = None
    if args.costs:
        with open(args.costs, encoding="utf-8") as fh:
            costs = json.load(fh)

    rows, columns = load_table(args.csv)
    ignored = {c.strip() for c in args.ignore.split(",") if c.strip()}
    columns = [c for c in columns if c not in ignored]
    enabled = [c.strip() for c in args.checks.split(",") if c.strip()]
    findings = _checks.run_checks(rows, columns, enabled)
    text = render(findings, len(rows), columns, source=args.csv, costs=costs)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"report written to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
