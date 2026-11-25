# data-quality-toolkit

[![tests](https://github.com/chirslin1225/data-quality-toolkit/actions/workflows/tests.yml/badge.svg)](https://github.com/chirslin1225/data-quality-toolkit/actions/workflows/tests.yml)

A small, dependency-free Python tool that scores the quality of a tabular dataset and reports **where the defects are and what they cost** — rather than just counting them.

Most data-quality libraries report one number per rule ("1,204 missing values"). That is not useful when one missing timestamp can break a downstream pipeline while one missing marketing tag costs nothing. `dqkit` lets you assign a **relative error cost** to each defect type, so the score reflects operational impact, not raw defect volume.

```
$ python -m dqkit examples/sample_sensor_data.csv --bootstrap 100
```

```
# Data Quality Report — `examples\sample_sensor_data.csv`

Rows: 5,038   Columns: 8

## Score: 32.3 / 100

_do not train on this without repair_

Row-level score: **69.7 / 100**, 95% interval **68.4 – 71.8** (100 subsamples of
2,519 rows, without replacement). `gap` is a property of the capture rather than
of a row, so it is excluded here and reported as a point value in the table.

| Rule | Column | Count | Rate | Cost | Burden |
|---|---|---:|---:|---:|---:|
| gap | `timestamp` | 1,202 | 19.27% | 4.0 | 0.77 |
| missing | `pressure_kpa` | 416 | 8.26% | 3.0 | 0.25 |
| constant | `firmware` | 5,038 | 100.00% | 0.1 | 0.10 |
| duplicate | `*` | 38 | 0.75% | 1.0 | 0.01 |
| dtype | `pressure_kpa` | 6 | 0.12% | 2.0 | 0.00 |
| outlier | `pressure_kpa` | 12 | 0.24% | 1.0 | 0.00 |
| dtype | `timestamp` | 2 | 0.04% | 2.0 | 0.00 |
```

Note the ordering: the single most expensive row is not the largest count. `firmware` touches every row but costs almost nothing to fix, so it sits below 416 missing pressure readings — which are what would actually break a downstream model.

## Quickstart

```bash
git clone https://github.com/chirslin1225/data-quality-toolkit.git
cd data-quality-toolkit
python -m dqkit examples/sample_sensor_data.csv
```

No dependencies. Python 3.9+.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

Regenerate the synthetic dataset at a different size:

```bash
python examples/make_sample.py --rows 20000
```

## Checks

| Rule | Default cost | What it counts |
|---|---:|---|
| `gap` | 4.0 | expected-but-absent samples in a regularly sampled timestamp column |
| `missing` | 3.0 | empty or whitespace-only cells |
| `dtype` | 2.0 | values that fail their column's type (declared or inferred) |
| `duplicate` | 1.0 | extra copies of a row |
| `outlier` | 1.0 | values outside the IQR fence |
| `constant` | 0.1 | columns that carry a single value |

## How the score works

For every finding, the tool computes a **burden**:

```
burden = defect_rate × error_cost
score  = 100 × exp(-Σ burden)
```

The exponential form means the score never goes negative, falls steeply for the first few serious defects, and flattens out as defects accumulate — which matches how data actually fails in practice.

`error_cost` defaults are in `dqkit/score.py` and can be overridden with `--costs my_costs.json`:

```json
{ "missing": 3.0, "duplicate": 1.0, "gap": 4.0 }
```

`constant` is deliberately cheap. A column with no variance is usually metadata (a fixed device id, a fixed firmware version); the repair is to drop the column, not to rescue rows. Because that finding's rate is always 1.0, giving it a high cost would let one harmless column bury every real defect. That is exactly the judgement the tool cannot make for you.

## The interval

`--bootstrap N` reports a 95% interval around the score by **repeated subsampling without replacement**.

Two deliberate choices, both of which change the number:

- **Without replacement, not a bootstrap.** Resampling with replacement manufactures duplicate rows by construction, which inflates the very defect the `duplicate` rule measures.
- **`gap` is excluded.** A gap is a property of the capture, not of a row: keeping half the rows randomly leaves roughly the same absolute number of missing samples while halving the expected count, so a row-level subsample reports a gap rate about twice the truth. Including it produced an interval that did not even bracket the point estimate, which is how the exclusion was found. Structural rules are reported as point values; the interval covers row-level defects, where subsampling is valid.

The known limitation: neither choice models *clustering*. A sensor that fails in runs rather than at random will produce a true spread wider than this interval suggests. A block bootstrap keyed on device or time would be the fix, and it is not implemented.

## CLI

```
python -m dqkit DATA.csv [options]

  --checks LIST        comma-separated checks to run (default: all)
  --costs FILE         JSON {rule: cost} overrides
  --ignore LIST        columns to exclude from the checks
  --out FILE           write the report to a file instead of stdout
  --list-checks        show the available checks

check tuning
  --time-col COL       column to treat as the timestamp (default: auto-detect)
  --interval SECONDS   expected sampling interval (default: median gap)
  --tolerance X        a diff over interval*tolerance counts as a gap (default 1.5)
  --fence X            IQR fence multiplier for outliers (default 1.5)
  --schema FILE        JSON mapping column -> float|int|date|str

  --bootstrap N        report a 95% interval from N subsamples (0 = off)
```

`--bootstrap 100` takes roughly 20 seconds on 5,000 rows and is mostly spent in the type check; drop to 50 for a quick look, or use `--checks` to narrow the rule set.

## Sample data

`examples/sample_sensor_data.csv` is **synthetic** — generated by `examples/make_sample.py` with known, injected defects (3 timestamp gaps, 38 duplicate rows, ~8.2% missing pressure readings, 6 junk values, 2 unparseable timestamps, 12 outliers, 1 constant column). A stereo-vision-inspired sensor schema was chosen because timestamp misalignment across modalities is a realistic and expensive failure mode. No real or company data is included anywhere in this repository.

## License

MIT — see [LICENSE](LICENSE).
