# Borealis first backtest — 2026-09-28

First real backtest of the composite signal on the local Intrinio
point-in-time panel. All figures below were computed by
`scripts/backtest_panel.py` (outputs in
`data/processed/backtest_first_2026-09-28/`); nothing is hand-waved.

## Specification

- **Universe:** all tickers with a non-NaN `z_composite` at rebalance
  (the factor-lab universe). 17,122 distinct tickers appear; ~8,700 held
  per month on average (5 equal-weight quintiles).
- **Dates:** 81 month-end signal dates 2020-01-31 → 2026-09-25;
  80 next-trading-day executions 2020-02-03 → 2026-09-01 (t+1 execution).
- **Signal:** `z_composite` — sleeve-weighted sector-neutral z-score
  (Quality 40 / Value 15 / Yield 15 / Momentum 15 / LowVol 10 / Size 5 /
  Growth 0; sector-neutral z, ±3σ winsorization, invalid `ev_ebitda` ≤ 0
  quarantined). One-trading-day signal lag (signal matrix shifted by 1 day).
- **Prices:** `adj_close` total-return (splits + dividends).
- **Costs:** 10 bps one-way. A dollar-neutral L/S pays costs on **both**
  legs: net spread = gross(Q5−Q1) − (turnover_Q5 + turnover_Q1) × cost.
- **Delistings:** 19,439/696,068 held position-months (2.79%) have a valid
  entry but no exit price. Diagnosed 2026-09-28: **76% of these are data
  gaps / ticker changes** (the ticker trades again later) — booked at 0%;
  the 24% that never trade again are booked at **−30%** (Shumway 1997),
  with a −100% rerun as the conservative bound. Classification uses price
  *existence* only → no return lookahead. (An earlier run booked every
  missing exit at −100%; it was discarded as indefensible.)
- **Corrupt-price defense:** per-period cross-sectional 1%/99%
  winsorization of holding returns (same treatment as the factor lab).
  Caught in testing: `CDT` adj_close printed 114,750,000 on 2023-11-01
  vs a raw close of 1.53 (≈+19M× monthly return). Uncorrected run discarded.
- **Benchmark:** equal-weight basket of the full signal universe,
  rebalanced on the same dates.

## Results (10 bps, main spec)

| Series | Ann. ret | Ann. vol | Sharpe | Max DD | Turnover/mo | Hit rate | Cumulative |
|---|---|---|---|---|---|---|---|
| L/S Q5−Q1, gross (0 bps) | +7.66% | 13.20% | 0.58 | −36.2% | 0.32 | 65.0% | +56.9% |
| **L/S Q5−Q1, net (10 bps)** | **+7.28%** | 13.20% | **0.55** | **−36.6%** | 0.32 | 62.5% | +52.9% |
| L/S, delist −100% bound | +7.67% | 13.21% | 0.58 | −36.5% | 0.32 | 63.7% | +56.9% |
| L/S, price ≥ $5 only | +6.55% | 13.43% | 0.49 | −33.8% | 0.33 | 56.2% | +45.4% |

- Cost-drag reconciliation: gross − net = 38 bps/yr; turnover-implied
  (0.323 × 10 bps × 12) = 38.7 bps/yr. **Matches.**
- Delist assumption moves the spread by only ~±0.4 pp/yr — the gap-vs-
  permanent split defused what was the biggest modeling risk.
- The edge survives the penny-stock filter: price ≥ $5 keeps Sharpe 0.49.
  (The microcap tail contributes, but does not drive, the result.)
- Annual L/S spread: 2020 −32.7% / 2021 +13.4% / 2022 +48.0% /
  2023 −2.5% / 2024 +5.5% / 2025 +8.6% / 2026 +21.2% (partial year).
  Max drawdown −36.6% troughs Feb 2021 (2020 factor/momentum reversal).
- Net quintile ann. returns: Q1 −8.2%, Q2 +1.1%, Q3 +5.5%, Q4 +4.4%,
  Q5 +0.5%. Monotonic except Q4 > Q5 — the edge is concentrated in
  **avoiding/shorting the bottom quintile**, not in the top quintile
  beating Q3/Q4.

## Long-only Q5 vs equal-weight benchmark (10 bps)

- Q5: +2.01% ann. Benchmark (EW universe): **−27.54% ann.**
  Active +29.7% ann, IR 0.76.
- The benchmark is an equal-weight basket of 17k names including thousands
  of sub-$1 stocks — it is **not investable** and its −27.5% is dominated
  by micro-cap decay and delist treatment. The +29.7% "active" is mostly
  "not holding micro-cap junk", not alpha vs a real benchmark. Do not
  quote without this context.

## Factor IC reference (from the lab, independent of this backtest)

- Composite 21-day rank IC: **+0.0549** (t = +3.42, hit 68.4%, n = 79).
- Sleeve ICs (2020-09-30 → 2026-09-25): Quality +0.0402 (t +5.88),
  Yield +0.0203 (t +2.89), Momentum +0.0176 (t +2.10),
  Value +0.0153 (t +1.98), LowVol +0.0123 (t +1.73),
  Size −0.0016 (t −0.22, insignificant — kept at 5% weight anyway).

## Caveats (read before quoting anything)

1. **Universe dependence.** The full universe includes ~15% sub-$5 names;
   the L/S result leans on shorting distressed microcaps that are
   expensive/impossible to borrow in practice. 10 bps one-way understates
   real trading costs for these names.
2. **Restatement lookahead.** Fundamentals use republication availability
   dates, but reported values embed later revisions — the panel is not
   perfectly point-in-time on values (documented in the panel notes).
3. **In-sample weights.** Sleeve weights were chosen after seeing the
   factor-efficacy lab results on the same sample — this backtest is not
   out-of-sample for the weighting choice.
4. **Single sample period** (2020-2026): COVID crash, meme rally, rate
   shock. One regime-heavy window; the −32.7% 2020 shows factor timing
   risk is real.
5. **Q5 ≠ best quintile.** The long leg (Q5, +0.5%) trails Q3 (+5.5%)
   and Q4 (+4.4%). A long-only product on this composite is not supported
   by the quintile profile; the evidence supports the L/S (or Q1-avoidance)
   framing only.
6. **Intrinio data is licensed.** Panel, outputs derived from it, and
   this note stay local; nothing here may be published or exfiltrated.

## Reproducibility

- `PYTHONPATH=src python3 scripts/backtest_panel.py --out data/processed/backtest_first_2026-09-28`
- Code: `src/borealis/backtest/panel_backtest.py`,
  `src/borealis/backtest/engine.py` (tests: `tests/test_panel_backtest.py`,
  43 passing). Raw and processed Intrinio inputs untouched.
- Corrections applied during this session (all in git history):
  dollar-neutral cost accounting (was crediting back the short leg's
  costs), gap-vs-permanent delist split (was blanket −100%),
  holding-return winsorization (CDT corrupt print), t+1 execution
  (was same-day signal).
