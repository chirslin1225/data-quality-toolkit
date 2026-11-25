"""Generate a synthetic sensor CSV with known, injected defects.

Everything here is invented. No real or company data is used or referenced.
The defects are planted on purpose so that ``python -m dqkit`` has something
to find and so the score is reproducible.

    python examples/make_sample.py            # writes examples/sample_sensor_data.csv
    python examples/make_sample.py --rows 20000
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import os
import random

COLUMNS = ["timestamp", "device_id", "frame_seq", "pressure_kpa",
           "accel_x", "accel_y", "accel_z", "firmware"]

MISSING_RATE = 0.082      # pressure_kpa dropouts
DUPLICATES = 38           # exact duplicate rows
GAPS = 3                  # long timestamp outages
BAD_VALUES = 6            # non-numeric junk in a numeric column
BAD_TIMES = 2             # unparseable timestamps
OUTLIERS = 12             # values far outside the IQR fence

JUNK = ["ERR", "-", "n/a", "NULL", "?", "98.6 kPa"]


def build(rows=5000, seed=7):
    rnd = random.Random(seed)
    start = dt.datetime(2026, 3, 1, 8, 0, 0)
    step = dt.timedelta(milliseconds=20)     # ~50 Hz
    data = []
    t = start
    gap_at = {rows // 4, rows // 2, (3 * rows) // 4}
    for i in range(rows):
        if i in gap_at:                      # skip a chunk -> a visible gap
            t += step * 400
        data.append({
            "timestamp": t.isoformat(timespec="milliseconds"),
            "device_id": f"EGO-{1 + i % 3:02d}",
            "frame_seq": i,
            "pressure_kpa": f"{98.0 + 1.5 * math.sin(i / 40) + rnd.uniform(-0.4, 0.4):.3f}",
            "accel_x": f"{rnd.uniform(-1, 1):.4f}",
            "accel_y": f"{rnd.uniform(-1, 1):.4f}",
            "accel_z": f"{rnd.uniform(-1, 1):.4f}",
            "firmware": "v2.3.1",            # constant column on purpose
        })
        t += step

    # dropouts
    missing_rows = rnd.sample(data, int(len(data) * MISSING_RATE))
    for r in missing_rows:
        r["pressure_kpa"] = ""

    # junk in a numeric column: counts as a type error, not as a missing value
    pool = [r for r in data if r["pressure_kpa"]]
    for r in rnd.sample(pool, BAD_VALUES):
        r["pressure_kpa"] = rnd.choice(JUNK)

    # unparseable timestamps
    for r in rnd.sample(data, BAD_TIMES):
        r["timestamp"] = "n/a"

    # gross outliers, well outside the IQR fence
    for r in rnd.sample(pool, OUTLIERS):
        r["pressure_kpa"] = rnd.choice(["41.200", "182.900"])

    # duplicate rows, appended so the originals survive
    for r in rnd.sample(data, DUPLICATES):
        data.append(dict(r))

    rnd.shuffle(data)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=5000)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "sample_sensor_data.csv"))
    args = ap.parse_args()

    data = build(args.rows)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(data)
    print(f"wrote {len(data):,} rows x {len(COLUMNS)} cols -> {args.out}")
    print(f"  injected: {GAPS} timestamp gaps, {DUPLICATES} duplicate rows, "
          f"~{MISSING_RATE:.1%} missing pressure_kpa, {BAD_VALUES} junk values, "
          f"{BAD_TIMES} unparseable timestamps, {OUTLIERS} outliers, 1 constant column")


if __name__ == "__main__":
    main()
