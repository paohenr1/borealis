# Borealis — Equity Factor Research

Borealis is a point-in-time equity factor research pipeline. It tests whether
common equity factors — value, momentum, quality, size, low volatility —
actually predict returns on large-cap US stocks, and publishes the answer
either way.

**Headline finding:** on 2020–2026 large caps, a long-only top-quintile factor
portfolio trails SPY by roughly 5%/yr after realistic costs (IR −0.68). The
ranking adds about nothing over an equal-weight large-cap portfolio. That is
the output of this project: an honest negative, not a flattering backtest.

It is a research project, not investment advice.

## How it works

1. **Ingest** — builds a point-in-time (date, ticker) panel. Fundamentals
   attach only once publicly available. No lookahead, ever.
2. **Factors** — value, quality, growth, momentum, low-vol, size, yield,
   all computed from point-in-time data.
3. **Scoring** — sector-neutral z-scores, winsorized; factor sleeves combined
   into a composite rank.
4. **Backtest** — lagged, costed quintile engine (10 bps one-way on measured
   turnover); delisted exits handled explicitly.
5. **Factor lab** — efficacy checks on every factor: rank IC, quintile
   spreads, turnover, regime conditioning.

163 passing tests. Every result reproducible from the scripts.

## Current status (2026-09-30)

- **Live model:** value / momentum / low-vol composite, monthly rebalance,
  518-stock universe (S&P 500 + Nasdaq-100 + Dow).
- **Tracked but unused:** quality, size, and growth are scored every run but
  carry zero weight, each with a written rule for reinstatement
  (see `config/factors.yaml`).
- **Research notes:** `notes/` holds dated snapshots; `reports/` holds
  generated reports including a drawdown autopsy.

## Quickstart

```bash
pip install -e .
python -m pytest tests/ -q

# Rank the live 518-name universe (Intrinio bulk data)
PYTHONPATH=src python scripts/rank.py --live --asof 2026-09-30 --top 25 \
    --out data/processed/scores_live_2026-09-30.csv
```

## Layout

```
config/          YAML: universe, factor weights, backtest params
src/borealis/    ingest/ factors/ scoring/ portfolio/ backtest/ lab/ reporting/
scripts/         rank.py · build_panel.py · backtest_panel.py · run_factor_lab.py
tests/           unit tests
notes/           dated research notes (historical snapshots)
reports/         generated reports
data/processed/  committed result summaries only (CSVs/JSON, kilobytes)
```

## Data

Market data is **licensed and NOT included**. Reproducing the panel needs
your own vendor data (Intrinio US bulk: prices + fundamentals + metadata;
see `scripts/fetch_intrinio_bulk.py`). Bulk zips are gitignored; the
manifest records the refresh. The CSV-input path (`scripts/rank.py --input`)
works with any export in the documented 17-column sector-block layout.
