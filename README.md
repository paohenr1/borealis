# Borealis — Factor Research Lab + Thin Ranking Engine

Borealis is a point-in-time equity factor research pipeline: a **research
lab** that tests whether factors work, and a **thin ranking engine** that
turns the lab's approved factors into a monthly ranking.

**Lab → Engine → Workflow.** The lab contains the intelligence (factor
efficacy, robustness checks, artifact detection, promotion gates for what
reaches production). The engine contains the rules (approved factors, a
predefined weighting policy, monthly ranking). The ranking is an attention
filter — which companies deserve a closer look — not a buy list.

It is a research project, not investment advice.

## Current state (2026-09-30)

- **Primary backtest:** long-only top-quintile vs SPY, 10 bps one-way on
  measured turnover. The long/short version is kept as a diagnostic;
  shorting was cut because the short book (small-cap junk) is largely
  unshortable and the modeled costs were fiction.
- **Live weights:** value 0.20, momentum 0.20, 126-day realized-vol low-vol
  0.10 (effective 0.40 / 0.40 / 0.20 after per-ticker renormalization).
  Quality, size, and growth are **zero-weight diagnostics** — still scored
  every run, each with a written reinstatement rule (see
  `config/factors.yaml`).
- **Honest verdict:** on 2020–2026 large caps the model trails SPY
  (~−5%/yr active, IR −0.68); the ranking adds ~nothing over an equal-weight
  large-cap portfolio. The lab's output is the honest negative, not a
  flattering backtest. Edges shouldn't be easy to find.
- **Tests:** 163 passing (`python -m pytest tests/ -q`).

## Quickstart

```bash
pip install -e .
python -m pytest tests/ -q

# Rank the live 518-name universe (S&P 500 + Nasdaq-100 + Dow, Intrinio bulk)
PYTHONPATH=src python scripts/rank.py --live --asof 2026-09-30 --top 25 \
    --out data/processed/scores_live_2026-09-30.csv
```

## Pipeline stages

1. **Ingest** (`src/borealis/ingest/`) — workbook loader plus an Intrinio
   bulk path: chunked streaming, schema/date/type validation, quarantine
   (never silent drops), de-duplication, clean Parquet. `panel.py` builds a
   point-in-time `(date, ticker)` panel — fundamentals attach only once
   publicly available (`merge_asof` on filing/calculable date), no lookahead.
2. **Factors** (`src/borealis/factors/`) — value, quality, growth, momentum,
   low-vol, size, yield. Higher = more attractive. Zero/negative P/E, P/S,
   P/B, EV/EBITDA are quarantined, never ranked "cheapest."
3. **Scoring** (`src/borealis/scoring/`) — winsorize ±3σ, z-score *within
   sector* (sector-neutral, magnitude-preserving), sleeve-weighted composite
   renormalized per ticker over available sleeves.
4. **Backtest** (`src/borealis/backtest/`) — lagged, costed quintile engine;
   signals shifted before trading; delisted exits handled (ticker-change
   gaps → 0%, permanent → −30% per Shumway 1997).
5. **Lab** (`src/borealis/lab/`) — factor efficacy: rank IC, horizons,
   quintile spreads, turnover, regime conditioning, correlation/PCA,
   broad-panel vs native large-cap universes.

## Layout

```
config/          YAML: universe, factor weights, backtest params
src/borealis/    ingest/ factors/ scoring/ portfolio/ backtest/ lab/ reporting/
scripts/         rank.py · build_panel.py · backtest_panel.py · run_factor_lab.py
tests/           unit tests
notes/           dated research notes (historical snapshots)
reports/         generated reports, incl. drawdown autopsy 2026-09-30
data/processed/  committed result summaries only (CSVs/JSON, kilobytes)
```

## Data

Market data is **licensed and NOT included**. Reproducing the panel needs
your own vendor data (Intrinio US bulk: prices + fundamentals + metadata;
see `scripts/fetch_intrinio_bulk.py`). Bulk zips are gitignored; the
manifest records the refresh. The workbook path (`scripts/rank.py --input`)
works with any export in the same 17-column sector-block layout.
