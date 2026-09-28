# Borealis review guide (2026-09-28)

A walkthrough of the codebase so you can internalize it before interviews.
Read a module's docstring, then the code — every non-obvious judgment call is
documented where it lives.

## Big picture

Borealis is a sector-relative multifactor equity research pipeline:
**ingest → factors → scoring → portfolio → backtest → lab**. Two data paths
feed it: a workbook snapshot (`scripts/rank.py`) and a point-in-time panel
built from vendor bulk data (`scripts/build_panel.py`). Config lives in
`config/*.yaml` — no hardcoded weights or parameters in code.

## 1. `ingest/` — getting data in without lying to yourself

- **`loader.py`** — parses the Ranks & Earnings workbook's UNIVERSE sheet.
  The sheet is a stack of per-sector blocks; columns are assigned
  **positionally** (not by header name) because the sheet reuses names
  ("PEG Ratio" and "Trailing Beta" each appear twice: raw metric + sub-rank).
  Key decision: positional schema, documented in `ORDERED_COLS`.
- **`validate.py`** — fail-fast checks on every ingest (required columns,
  non-empty universe, sane types). "Fail fast, fail loud."
- **`intrinio_bulk.py`** — chunked loader for vendor bulk zips (prices,
  fundamentals, companies). Streams in chunks, validates schemas/dates/types,
  **quarantines bad rows with a logged report (never silently drops)**,
  de-duplicates. Verified facts baked into the docstring: `ADJ_CLOSE` is
  split- *and* dividend-adjusted (total-return basis, checked on NVDA's 2024
  10:1 split); ~0.26% of (ticker, date) rows are duplicates across security
  records; delisted securities are present (no survivorship hole); restated
  fundamental vintages carry their *republication* filing date.
- **`panel.py`** — builds the point-in-time `(date, ticker)` panel.
  Fundamentals attach via `merge_asof` on `available_date` (later of filing
  date / first-calculable date): each date only sees data that was public by
  then. **Caveat to know cold:** restated vintages are point-in-time correct
  on *availability* but embed future *revisions* — mild lookahead on values,
  none on availability. Delisted names are kept; their series just ends.

## 2. `factors/` — one module per factor, all oriented higher = better

- **`value.py`** — cheap on P/E, P/S, PEG. **The critical rule:** a ratio of
  zero or negative is quarantined as NaN (then sector-median imputed) — it is
  *never* ranked as "cheapest". This was the workbook's original sin
  (16 zero-P/E names ranked cheapest).
- **`quality.py`** — ROE, FCF margin, leverage. Degrades gracefully to all-NaN
  when the feed lacks those columns — and the composite renormalizes weights
  over the remaining factors. "Add the data and it just works."
- **`growth.py`** — trailing quarterly sales growth, sector-median imputed.
- **`momentum.py`** — workbook path uses distance above the 52-week low (a
  documented placeholder); the panel path uses proper 12-1 trailing total
  return (`lab/price_proxies.py`), skipping the most recent month to avoid
  short-term reversal contamination.
- **`lowvol.py`** — lower trailing beta preferred (sign flipped so higher =
  calmer).

## 3. `scoring/composite.py` — sector-neutral, magnitude-preserving

Per factor: winsorize at ±3σ within sector → z-score within sector →
weighted average → rank 1 = most attractive *in its sector*. Two deliberate
choices: (a) z-scores instead of ordinal rank-sums, so a stock that's far
cheaper counts as far cheaper; (b) all scoring is within-sector, so you're
never just buying "cheap sectors".

## 4. `portfolio/construction.py` — from scores to a portfolio

Quintile formation (`qcut`, 1 = least attractive), position caps (5%) and
sector caps (30%), turnover-aware rebalancing. Plumbing that keeps a paper
portfolio honest about concentration.

## 5. `backtest/` — the credibility core

- **`engine.py`** — costed quintile backtest. The discipline: a signal dated
  *t* may only drive positions from *t + signal_lag* onward — no lookahead
  **by construction**, not by carefulness. Equal-weighted quintiles, one-way
  costs charged on measured turnover.
- **`panel_backtest.py`** — first real backtest driver: month-end rebalance
  dates from the panel's own trading calendar, t+1 execution, long-short
  Q5−Q1 plus long-only Q5 vs an equal-weight benchmark.
- **Delist handling** (know this): exits are classified by whether the ticker
  trades again later — data gaps/ticker changes (76%) → 0%, permanent
  disappearances → −30% (Shumway 1997). A blanket −100% produced absurd
  results and was diagnosed, not assumed.
- **Result (in-sample):** Feb 2020 → Sep 2026, 10 bps: L/S +7.3%/yr, Sharpe
  0.55, max DD −36.6%, IC +0.055. The edge is in *avoiding/shorting Q1*,
  not in picking winners. Quote the methodology, never the numbers, on a
  resume.

## 6. `lab/` — factor efficacy

- **`ic.py`** — cross-sectional Spearman rank IC per factor per date; z(t)
  only ever meets forward returns after t.
- **`horizons.py` / `halflife.py`** — IC decay across 21/63/126/252-day
  horizons; half-life via rank autocorrelation. Honest anomaly on record:
  IC *rises* with horizon here (survivorship ruled out as the cause).
- **`quintiles.py`** — per-date Q5−Q1 spreads; forward returns winsorized at
  1/99 per date because the micro-cap tail contains +10000% 21-day moves.
- **`sleeve_backtest.py`** — each sleeve through the same costed engine on
  its own coverable universe (price sleeves cover ~22.6k names, fundamental
  sleeves ~5.9k — spreads aren't directly comparable across sleeves).
- **`regimes.py`** — SPY-trailing-return up/down and realized-vol high/low
  buckets (no VIX in the bulk data; realized vol is the documented proxy).
  Finding: yield/low-vol/size/value degrade in high-vol regimes; momentum
  doesn't. Low-vol is pro-cyclical — backwards for a "defensive" sleeve.
- **`corrpca.py`** — no sleeve pair above +0.40 Spearman; PC1 only 29% —
  no redundancy.
- **Verdicts:** keep quality / value / momentum; down-weight low-vol; drop
  growth (already zero-weighted). Full tables in
  `notes/factor_lab_2026-09-28.md`.

## 7. `reporting/tearsheet.py` — show your work

Top-N tables per sector with the composite and its drivers — the "why does
this stock rank here" answer.

## Scripts (entry points)

| Script | Does |
|---|---|
| `scripts/rank.py` | Score a workbook universe → `data/processed/scores.csv` |
| `scripts/build_panel.py` | Bulk zips → clean Parquet → PIT panel (3 stages, resumable) |
| `scripts/backtest_panel.py` | First real backtest → `data/processed/backtest_first_*/` |
| `scripts/run_factor_lab.py` | Full efficacy lab → `data/processed/factor_lab_*/` |
| `scripts/lab.py` | Lighter lab CLI (`efficacy` / `corrpca` modes) → `reports/` |

## Likely interview questions this codebase equips you to answer

1. Walk me through a project you built end-to-end.
2. How do you prevent lookahead bias in a backtest? (signal lag by
   construction; as-of joins on `available_date`; t+1 execution)
3. How do you handle delisted / bankrupt names? (gap-vs-permanent
   classification; Shumway −30%; no survivorship filter — delisted names stay)
4. Why sector-neutral scoring instead of raw ranks? (z-scores preserve
   magnitude; sector-neutral avoids "cheap sector" bets)
5. Your backtest shows +7.3% — should I believe it? (in-sample weights,
   restatement lookahead, 10 bps understates micro-cap shorting costs,
   regime-heavy window — the honest answer is the point)
6. How do you know your factors aren't all the same bet? (sleeve correlation
   ≤ 0.40, PCA PC1 29%)
7. What breaks in high-volatility regimes? (yield/low-vol/size/value degrade;
   momentum holds — from the regime lab)
8. How do you test data pipelines? (chunked validation, quarantine-not-drop
   with logged reports, 56 unit tests incl. PIT-violation checks)
