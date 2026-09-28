# Borealis — Sector-Relative Multifactor Equity Research Pipeline

Borealis turns a manual stock-ranking spreadsheet into a tested, point-in-time
research pipeline:

**ingest → factor library → sector-neutral scoring → portfolio construction → costed backtest → factor efficacy lab**

It is a research project, not investment advice. Backtest figures reported in
`notes/` are historical and, where noted, in-sample.

## Quickstart

```bash
pip install -e .

# Run the test suite (unittest; 56 tests)
python -m unittest discover -s tests

# Rank the sample workbook universe as of 2026-09-22
PYTHONPATH=src python scripts/rank.py \
  --input data/raw/ranks_earnings_2026-09-22.xlsx \
  --asof 2026-09-22 --top 5
```

The sample workbook is licensed data and is **not** included in this repo.

## Pipeline stages

1. **Ingest** (`src/borealis/ingest/`) — positional parser for the Ranks &
   Earnings workbook plus fail-fast validation. A separate bulk path
   (`intrinio_bulk.py`) streams vendor bulk downloads in chunks: validates
   schemas/dates/types, quarantines bad rows (never silently drops),
   de-duplicates, and writes clean Parquet. `panel.py` then builds a
   point-in-time `(date, ticker)` panel — fundamentals attach only once they
   were publicly available (`merge_asof` on filing/calculable date), so
   signals can't peek at the future.
2. **Factors** (`src/borealis/factors/`) — value, quality, growth, momentum,
   low-vol. Every factor is oriented so higher = more attractive.
3. **Scoring** (`src/borealis/scoring/`) — winsorize at ±3σ, z-score *within
   sector* (sector-neutral, magnitude-preserving), weighted composite.
   Factors with no data degrade gracefully to zero weight.
4. **Portfolio** (`src/borealis/portfolio/`) — quintile formation, position and
   sector caps, turnover measurement.
5. **Backtest** (`src/borealis/backtest/`) — lagged, costed quintile engine.
   Signals are shifted before trading (no lookahead by construction);
   one-way costs charged on measured turnover; delisted exits handled
   (ticker-change gaps → 0%, permanent → −30% per Shumway 1997).
6. **Lab** (`src/borealis/lab/`) — factor efficacy: rank IC, IC half-life,
   quintile spreads, turnover, regime conditioning, correlation/PCA.

## Repo layout

```
config/          YAML: universe, factor weights, backtest params (no hardcoded values in code)
src/borealis/
  ingest/        workbook loader + validation; intrinio_bulk.py; panel.py
  factors/       value, quality, growth, momentum, lowvol — one module each
  scoring/       winsorize, sector z-scores, composite
  portfolio/     quintile formation, caps, turnover-aware rebalancing
  backtest/      engine.py (lagged, costed); panel_backtest.py (PIT driver)
  lab/           IC, horizons, regimes, sleeves, correlation/PCA
  reporting/     tear sheets, factor attribution
scripts/         rank.py (workbook CLI) · build_panel.py · backtest_panel.py ·
                 run_factor_lab.py · lab.py
tests/           unit tests (unittest)
notes/           dated research notes: backtest results, factor lab, review guide
reports/         generated factor-efficacy reports (small, derived)
data/processed/ committed result summaries only (CSVs/JSON, kilobytes)
```

## Results so far

- First backtest on the point-in-time panel (Feb 2020 → Sep 2026, monthly,
  10 bps one-way): long/short Q5−Q1 **+7.3%/yr, Sharpe 0.55, max DD −36.6%**,
  signal IC **+0.055**. The edge is mostly in avoiding/shorting the bottom
  quintile, not in picking winners. See `notes/first_backtest_2026-09-28.md`.
- Factor lab verdicts: **keep** quality / value / momentum, **down-weight**
  low-vol, **drop** growth. Sleeve spreads and IC tables in
  `notes/factor_lab_2026-09-28.md`.
- Caveats apply: composite weights were chosen in-sample, restated
  fundamentals embed later revisions, 10 bps understates micro-cap shorting
  costs, and 2020–2026 is a regime-heavy window. Full caveat lists live in
  the notes.

## Data

Market data is **licensed and NOT included** in this repo. To reproduce the
panel and backtest you need your own vendor data:

- An Intrinio subscription with US bulk downloads (prices + fundamentals),
  then `PYTHONPATH=src python scripts/build_panel.py --raw <zips> --out
  data/processed/intrinio`. The ingest path is vendor-specific but small —
  adapt `intrinio_bulk.py` to another source and the rest of the pipeline is
  unchanged.
- The `data/raw/` workbook path (`scripts/rank.py`) works with any export in
  the same 27-column sector-block layout; see `ingest/loader.py`.

## Methodology notes (v0.1)

- **Zero or negative P/E / PEG is treated as missing, never as "cheapest."**
  Missing values are sector-median imputed. (The source workbook's zeros were
  previously ranked as the cheapest stocks — the original sin this project
  fixes.)
- Ordinal rank-sums are replaced by z-scores: magnitude-preserving and
  sector-neutral.
- Quality auto-excludes itself (zero weight, renormalized) until ROE/FCF/
  leverage data exists.
