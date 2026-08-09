# PIREP Turbulence Classifier — Phase 0 & 1

Data collection infrastructure for the turbulence-from-text project.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install pandas requests
```

Set your identifier in **both** files (AWC asks for a custom User-Agent or
automated traffic may get filtered):

```python
USER_AGENT = "pirep-turbulence-<yourname>"
```

## Step 1 — Phase 0: discover the schema

```bash
python explore.py
```

Prints the real column names, PIREP-vs-AIREP breakdown, turbulence label
yield, and sample reports. Saves `snapshot.csv` so you can build the parser
offline afterwards.

**Read the sample reports.** This is the step people skip and then lose three
days debugging a parser against assumptions they never checked.

Then copy the resolved column names into `COLUMNS` in `collector.py`.
Auto-resolution works if AWC uses a name in the candidate list, but pinning
them explicitly means a schema change fails loudly instead of silently.

## Step 2 — Phase 1: start collecting

```bash
python collector.py --once     # verify one pull works
python collector.py            # continuous, every 10 min
python collector.py --stats    # check progress anytime
```

Start this today. AWC only serves the previous 15 days, so the dataset accrues
in real time — it is the bottleneck for the whole project.

Run it somewhere that stays up. A sleeping laptop means gaps in the record.

### Getting reports/day

Run `--stats` 24h apart and diff the totals. That number decides whether Phase 5
fits your schedule.

## Design decisions worth knowing

**Dedup key is a hash of (obs_time + lat + lon + raw_text).** `pirepId` was
removed from AWC output in Sept 2025 so it cannot be used. The cache is a
rolling snapshot — every poll re-serves reports you already have. Without
dedup you build a duplicate-laden dataset that leaks across your train/test
split and inflates your metrics.

**Every row is stored twice:** extracted into typed columns, and whole as
`raw_json`. If a column guess turns out wrong you re-parse from the database
instead of re-collecting for another three weeks.

**204 is not an error.** It means a valid request with no new data. 429 means
rate-limited; the collector backs off exponentially. AWC caps at 100 req/min
and asks for no more than 1 req/min per thread.

## Backups

```bash
sqlite3 pireps.db ".backup 'pireps_backup.db'"
```

Weeks of accrued data with no backup is the worst way to lose this project.

## Tests

```bash
python test_collector.py
```

Validates column resolution, dedup on repeat and partial-overlap pulls, field
extraction, `raw_json` completeness, and missing-column handling — all against
synthetic data, no network needed.

## Next: Phase 2

Once a few days of data are in, build the parser and label mapper against
`snapshot.csv`. Two decisions waiting for you:

1. **Label scheme.** Collapse to 4 classes (None/Light/Moderate/Severe),
   taking max severity from combos like `LGT-MOD`.
2. **AIREP filtering.** Automated reports carry no prose. Check the
   `report_type` distribution and decide whether to exclude them — training a
   language model on empty strings will quietly destroy your results.

**Label leakage warning:** strip the `/TB` field from `raw_text` before it
reaches the model. Otherwise it learns to read the answer, not the language.
