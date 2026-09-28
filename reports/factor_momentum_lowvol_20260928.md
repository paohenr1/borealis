# Borealis Lab Addendum — Momentum & Low-Vol Validation, Yield Sleeve, Revised Composite

_Generated 2026-09-28 · closes the two open design questions from
factor_changes_20260928.md. Panel untouched (read-only); `config/factors.yaml`
(workbook pipeline) untouched._

## 1. Proxy constructions

Both proxies are built from daily split/dividend-adjusted closes
(`data/processed/intrinio/prices_clean.parquet`), so they cover the full
price universe (~22.6k tickers), unlike fundamental factors (~5.9k).
Code: `src/borealis/lab/price_proxies.py`.

| proxy | formula | orientation |
|---|---|---|
| `mom_12m1m` | `adj_close(t−21) / adj_close(t−252) − 1` | higher = better |
| `vol_126d` | sample std (ddof=1) of daily simple total returns over the 126 trading days ending at t, × √252 | lower = better |

Judgment calls (one line each):
- 12-**1**, not 12-0: the most recent month is skipped to avoid short-term reversal contamination (standard).
- Offsets are per-ticker **trading days** (row positions), so gappy/delisted histories are handled naturally.
- Momentum needs 252 trading days of history → its sample starts ~2021-02 (n=67 vs 79 for other sleeves); vol needs 126 → n=73.
- **No lookahead**: every input is a price on or before t (momentum's latest input is t−21); verified by test.
- Both enter the lab through the standard pipeline: oriented, winsorized ±3σ, sector-neutral z-scored (same house convention as fundamentals).

## 2. Efficacy verdicts

Same battery as the main lab: 81 month-end rebalance dates (fewer for the
proxies, see above), rank ICs vs forward total returns, quintile spreads,
half-life.

| factor | IC₂₁ | t | n | IC₆₃ t | Q5−Q1₂₁/mo | half-life |
|---|---|---|---|---|---|---|
| mom_12m1m | +0.0533 | **+3.43** | 67 | **+6.09** | +1.24% (t=2.24) | 116d |
| vol_126d | +0.0579 | **+2.84** | 73 | **+3.18** | +0.86% (t=1.01) | >252d |

- **Momentum VALIDATES.** t=+3.43 at 21d, strengthening to t=+6.09 at 63d — the signal predicts 3-month returns better than 1-month, which supports a monthly-or-slower rebalance (its 116d half-life agrees).
- **Low-vol VALIDATES, marginally.** t=+2.84/+3.18; economically the right sign and consistent across horizons, but the weakest of the validated set — hence a 0.10 weight, not 0.15.
- Both had been carried at 0.20/0.15 on faith; they now carry those weights on evidence.

## 3. Sleeve-level ICs (21d) — the weight evidence

| sleeve | members | IC t-stat | hit rate |
|---|---|---|---|
| quality | roe, roa, profit_margin, fcf, bvps, asset_turnover, debt_ebitda, leverage | +5.88 | 75% |
| size | enterprise_value (regime-flipped) | +5.43 | 72% |
| yield | div_yield | +5.12 | 73% |
| value | earn_yield, ev_ebitda | +3.70 | 63% |
| momentum | mom_12m1m | +3.43 | 67% |
| lowvol | vol_126d | +2.84 | 59% |
| growth | rev_growth, ebitda_growth, ebit_growth | −0.11 | 48% |

## 4. div_yield decision: standalone yield sleeve

**Decision: standalone `yield` sleeve** (implemented in `SLEEVES`).
Justification: div_yield (t=+5.12) is the 5th-strongest signal and loads on
its own PCA axis (PC5); folding it into value would re-concentrate the
cheapness exposure the value consolidation just removed.

## 5. Revised composite

Weights (`src/borealis/lab/composite.py::SLEEVE_WEIGHTS`):

| sleeve | old | new | why (one line) |
|---|---|---|---|
| quality | 0.40 | **0.40** | strongest sleeve (t=5.88), genuinely diversified |
| value | 0.20 | **0.15** | consolidated sleeve validates (t=3.70); room for yield |
| growth | 0.05 | **0.00** | three consecutive \|t\|<2 — cut the toe-hold |
| yield | — | **0.15** | new standalone sleeve (t=5.12) |
| momentum | 0.20 | **0.15** | validates; shorter history argues against more |
| lowvol | 0.15 | **0.10** | validates but weakest of the validated set |
| size | — | **0.05** | strong in-sample (t=5.43) but regime-fit; small bet + flip-back rule |

Composite = sleeve-weighted mean of sleeve z-scores, renormalized per
ticker across sleeves present (early dates lack momentum; pairwise-complete
within sleeves).

| composite | IC₂₁ | t | hit | IC₆₃ t | spread₂₁/mo | half-life |
|---|---|---|---|---|---|---|
| 7-sleeve (new weights) | +0.0549 | +3.42 | 68% | +4.14 | +0.57% | 161d |
| 3-sleeve (prior) | +0.0455 | +6.06 | 75% | — | — | — |

**Honest read:** mean IC rose (+0.0455 → +0.0549) but the t-stat fell
(6.06 → 3.42). The extra sleeves add IC variance — they share the PC1
value-profitability axis (per the corrpca report), so diversification
across sleeves buys less than the sleeve count suggests, and momentum's
shorter history adds noise. The 7-sleeve composite has higher expected IC;
the 3-sleeve version was smoother. This is the documented trade, not a bug.

## 6. Judgment calls

- Sleeve means are pairwise-complete (a ticker missing one metric still scores).
- Growth cut to zero rather than kept as a toe-hold — three strikes.
- Size kept at 0.05 (not dropped): the flip-back rule (revert if size IC turns positive over trailing 12m) makes it a monitored bet, not a blind one.
- Composite renormalizes per ticker when sleeves are missing (early momentum gap).

## 7. Remaining concerns for a hiring manager

- The composite t-stat regression (6.06 → 3.42) deserves a slide of its own: it is the empirical cost of sleeve proliferation under a shared risk axis.
- Momentum's 63d-vs-21d gap (t=6.09 vs 3.43) suggests the rebalance/holding-period design should be sleeve-specific, not one-size-fits-all.
- Small caps remain price-only: momentum/lowvol verdicts cover the full universe, but quality/value/yield verdicts are large/mid-cap verdicts.
- The size flip is still the most regime-sensitive call; the flip-back rule is documented but not automated.
- 37% "unknown" sector bucket and restated-value caveats carry over unchanged.
