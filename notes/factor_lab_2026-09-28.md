# Factor efficacy lab — 2026-09-28

Per-sleeve diagnosis of the seven Borealis sleeves under the **same
specification as the first backtest** (see
`notes/first_backtest_2026-09-28.md`). This lab answers: which sleeves
earn their weight, where the spread comes from (long vs short leg), how
fast the signal decays, and how it behaves across market regimes.

Outputs: `data/processed/factor_lab_2026-09-28/` (CSVs + `summary.json`).
Driver: `scripts/run_factor_lab.py`. Method modules:
`src/borealis/lab/sleeve_backtest.py`, `horizons.py`, `regimes.py`
(+ `corrpca.py` rank-correlation support).

## Specification (identical to the first backtest)

- Month-end signals, next-trading-day execution, one-day signal lag.
- Each sleeve run standalone on its own coverable universe (tickers with
  non-NaN sleeve z at rebalance): value ~3.2k, quality ~4.1k,
  growth ~3.9k, yield ~4.1k, size ~4.0k, momentum ~8.9k, lowvol ~9.5k
  names/month. Fundamentals cover fewer names than price signals —
  sleeve universes differ by construction.
- Equal-weight quintiles, Q5−Q1 spread; **10 bps one-way on both legs**.
- Delisting: 0% when the ticker trades again later, **−30% for
  permanent disappearance** (Shumway-style).
- Per-period 1st/99th percentile holding-return winsorization.
- Adjusted total-return prices (`adj_close`).
- Period: 80 trade months, Feb 2020 – Sep 2026 (momentum: 68 months —
  needs 12 m history; lowvol: 74 months — needs 126 d history).

## Costed Q5−Q1 spreads (10 bps, per-annum)

| Sleeve | Spread | Vol | Sharpe | Max DD | L/S turn | Hit | Q1 | Q3 | Q5 |
|---|---|---|---|---|---|---|---|---|---|
| Quality | **+15.2%** | 11.7% | **1.29** | −11.3% | 0.25 | 66% | −5.7% | +2.8% | +9.7% |
| Momentum | **+12.4%** | 11.2% | **1.10** | −15.0% | 0.41 | 74% | −10.2% | +3.4% | +2.6% |
| Value | **+11.2%** | 10.1% | **1.11** | −11.9% | 0.30 | 65% | −1.2% | +8.9% | +10.4% |
| Size* | +11.1% | 12.2% | 0.91 | −25.8% | 0.14 | 64% | +0.8% | +1.2% | +12.0% |
| Low vol | +10.1% | 14.7% | 0.69 | −26.2% | 0.28 | 55% | −9.3% | +8.8% | +1.1% |
| Yield | +5.5% | 18.1% | 0.31 | −43.0% | 0.13 | 51% | +5.7% | −2.5% | +11.4% |
| Growth | +0.6% | 7.4% | 0.07 | −28.5% | 0.32 | 55% | +4.6% | +2.7% | +5.5% |

\* "Size" is tested **large-cap-tilted**: `enterprise_value` direction was
flipped to +1 on 2026-09-28 after large caps outperformed 2020–2026
(documented in `preprocess.py`). Its spread is a large-cap premium, not
the classic small-cap premium.

## Long-leg vs short-leg decomposition

`long_contrib = Q5−Q3`, `short_contrib = Q3−Q1` (share of spread from
avoiding/shorting Q1):

- **Value** — short 87%: Q1 (−1.2%) lagged badly; long leg barely beats
  the middle quintile (+1.5% of the +11.2%).
- **Quality** — balanced: short 55% / long 45%. The only sleeve where
  both legs clearly contribute.
- **Momentum** — short 107%: the entire spread (and then some) is
  avoiding Q1 (−10.2%); Q5 (+2.6%) slightly *trails* Q3 (+3.4%).
- **Low vol** — short 174%: spread is purely "don't own the most
  volatile names" (Q1 −9.3%); Q5 (+1.1%) trails Q3 (+8.8%) by a wide
  margin.
- **Size** — long 96%: large caps (Q5 +12.0%) did all the work; Q1≈Q3.
- **Growth** — short −204%: Q1 (+4.6%) *outperformed* Q3 (+2.7%) — the
  short leg actively destroys value; the tiny +0.6% spread is all long.
- **Yield** — short −144%: quintiles are non-monotonic (Q1 +5.7% >
  Q3 −2.5%); the sort doesn't capture what the IC sees.

Pattern matches the composite finding: most spread comes from the
short/avoidance leg, except quality (balanced) and size (long leg).

## IC at 1/3/6/12-month horizons and half-life

Spearman IC of sleeve z(t) vs forward total return over 21/63/126/252
trading days (n = 79/77/74/68 months):

| Sleeve | IC 21d (t) | IC 63d | IC 126d | IC 252d | Half-life |
|---|---|---|---|---|---|
| Quality | **+0.051 (+5.88)** | +0.067 | +0.083 | +0.097 | > 252 d (censored) |
| Yield | **+0.053 (+5.22)** | +0.070 | +0.088 | +0.108 | > 252 d (censored) |
| Size | **+0.060 (+5.43)** | +0.085 | +0.102 | +0.122 | > 252 d (censored) |
| Low vol | +0.055 (+2.74) | +0.062 | +0.080 | +0.101 | > 252 d (censored) |
| Momentum | **+0.053 (+3.37)** | +0.083 | +0.108 | +0.103 | > 252 d (censored) |
| Value | **+0.038 (+3.71)** | +0.052 | +0.072 | +0.101 | > 252 d (censored) |
| Growth | −0.001 (−0.15) | −0.002 | −0.003 | −0.007 | n/a (no signal) |

Two things stand out, both documented rather than smoothed over:

1. **IC rises with horizon** instead of decaying. A check rules out the
   obvious artifact: quality's 21 d IC on the 252 d-survivor subsample
   is +0.047 vs +0.051 full-sample — survivorship conditioning does not
   explain it. The consistent reading is a *persistent cross-sectional
   drift premium*: the signal's predictive component compounds roughly
   linearly while idiosyncratic noise diversifies as √h, so rank
   correlation with cumulative return grows with h.
2. **Long-horizon t-stats are overstated.** Monthly 252 d IC
   observations overlap ~11 neighboring months, so effective N is far
   below 68; treat 126/252 d t-stats as directional, not significance
   tests (Newey–West not applied — flagged as a follow-up). The 21 d IC
   is the clean efficacy read.
3. Half-life is censored above 252 d for every working sleeve — the
   honest statement is "no measurable decay within one year in this
   sample," not a point estimate.

## Regimes

SPY-based: up/down = trailing-21 d SPY total-return sign (53 up / 25
down months in the IC sample); high/low vol = trailing-63 d realized SPY
vol vs its median (39/39). No VIX series exists in the bulk data, so
realized vol is the documented proxy.

**Up vs down months:** no sleeve shows a significant IC difference
(all |t| < 1.0). Spreads are positive in both regimes for every sleeve
except growth (−3.1% in down months) and low vol (−2.0% in down
months).

**High vs low vol — this is where sleeves separate:**

| Sleeve | IC high-vol | IC low-vol | diff t | Spread high-vol | Spread low-vol |
|---|---|---|---|---|---|
| Yield | +0.029 | +0.085 | **−2.83** | −5.3% | +13.4% |
| Low vol | +0.011 | +0.099 | **−2.24** | +0.7% | +18.9% |
| Size | +0.037 | +0.082 | **−2.01** | +1.5% | +22.0% |
| Value | +0.027 | +0.060 | −1.64 | +8.8% | +18.1% |
| Quality | +0.044 | +0.062 | −1.00 | +10.4% | +21.4% |
| Growth | +0.001 | −0.006 | +0.62 | −0.6% | +1.4% |
| Momentum | +0.067 | +0.041 | +0.80 | +12.3% | +12.3% |

Fundamental sleeves (yield, low vol, size, value) degrade materially in
high-vol regimes; quality degrades mildly; **momentum is the only
sleeve that doesn't** (flat spreads, IC if anything better). For a
defensive sleeve, low vol's profile is backwards: +16.2% spread in up
months, −2.0% in down months, and its IC collapses exactly when
volatility spikes.

## Correlation / redundancy

Average monthly Spearman rank correlation across sleeves (Fisher-z
averaged). Top pairs: yield/lowvol +0.39, lowvol/size +0.38,
value/quality +0.28, yield/size +0.27, quality/lowvol +0.27. No pair
above 0.40. PCA on the sleeve correlation matrix: PC1 29%, PC1–3 61% —
no dominant axis, no redundancy flag at the sleeve level. (The
yield/lowvol/size-large cluster is the familiar defensive-large-cap
dividend nexus, not a data error.)

## Verdicts (evidence only)

- **Quality — KEEP (strongest).** Best spread (+15.2%, Sharpe 1.29),
  strongest 21 d IC (t +5.88), only sleeve with both legs contributing,
  mildest high-vol degradation, works in up and down months.
- **Value — KEEP.** +11.2% spread, Sharpe 1.11, IC t +3.71. Caveats:
  87% short-side driven, and it fades in high-vol regimes (IC 0.027 vs
  0.060) — size the weight for that.
- **Momentum — KEEP, watch turnover.** +12.4% spread, Sharpe 1.10,
  highest hit rate (74%), regime-robust — the only sleeve immune to the
  high-vol fade. But: 0.41 L/S turnover (highest), 68 months of history
  (shortest), and the spread is 100%+ short-side; at higher realistic
  costs it degrades first.
- **Low vol — DOWN-WEIGHT.** +10.1% spread flatters it: Sharpe 0.69,
  weakest significant IC (t +2.74), spread is 174% short-side with the
  long leg trailing Q3, pro-cyclical in this sample (+16.2% up months /
  −2.0% down months), and its IC vanishes in high-vol regimes
  (0.011 vs 0.099, t −2.24). A defensive factor that fails when defense
  is needed should not carry 10%.
- **Growth — DROP.** +0.6% spread, Sharpe 0.07, IC ≈ 0 at every horizon
  (t −0.15 at 21 d), negative short-side contribution. Already at zero
  weight in the composite — this lab confirms that call.

Supplemental (not among the five requested): **yield** has a top-tier IC
(t +5.22) that the quintile spread fails to monetize (non-monotonic
quintiles, −43% max DD, collapses in high vol) — keep as a research
signal, not a spread sleeve. **Size** as tested is a large-cap tilt
(+11.1% spread, entirely long-side); keep the 5% only with the
documented flip-back rule and a micro-cap cost caveat.

Implication for the composite (currently value .15 / quality .40 /
growth 0 / yield .15 / momentum .15 / lowvol .10 / size .05 — weights
chosen in-sample, see caveat): the evidence supports quality ≥ value ≥
momentum as the core, low vol cut well below 10%, growth at zero.

## Caveats (carried forward)

- Fundamentals retain **mild restatement lookahead** despite
  point-in-time availability discipline.
- 2020–2026 is short and regime-heavy (COVID crash, rate shock,
  AI-cycle concentration); up/down and vol splits are 25–53 months.
- **10 bps understates micro-cap trading and short-borrow costs** —
  most binding for momentum (turnover 0.41) and the small-cap tail.
- Sleeve universes differ (3–4k fundamental names vs ~9k price-signal
  names); cross-sleeve comparisons are not on identical samples.
- Composite weights were chosen in-sample after seeing factor efficacy;
  treat weight implications as hypotheses, not findings.
- Long-horizon IC t-stats ignore overlapping-window autocorrelation.
- Intrinio data and derived outputs are licensed — local only.
