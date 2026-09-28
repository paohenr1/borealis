# Borealis Factor Structure: Correlation + PCA

_Generated 2026-09-28T16:00:04+00:00 · panel data/processed/intrinio/panel · 81 monthly rebalance dates (2020-01-31 → 2026-09-25)_

## Sampling scheme
- Rebalance dates: month-end trading days in the panel (81 dates, 2020-01-31 to 2026-09-25).
- Factors oriented (higher = more attractive), zero/negative value ratios quarantined, winsorized at ±3σ and z-scored within (date, sector); 'unknown' sector kept as its own bucket.
- Per-date Pearson correlation of z-scores (pairwise complete, min_periods=200; dates with <200 rows skipped), Fisher-z averaged back to correlation space; forced symmetric, unit diagonal.
- PCA on the date-averaged correlation matrix (purely cross-sectional; pooled z-scores would let high-volatility dates dominate).
- Redundancy: greedy clusters at |corr| ≥ 0.70; cluster keeper = highest |IC t-stat| from the efficacy lab (from reports/factor_efficacy_20260928.json).

## Mean cross-sectional correlation matrix (Fisher-z averaged)

| factor | pe | pb | ps | ev_ebitda | ev_ebit | ev_fcff | earn_yield | roe | roa | ebitda_margin | profit_margin | fcf | bvps | asset_turnover | debt_ebitda | leverage | rev_growth | ebitda_growth | ebit_growth | div_yield | market_cap | enterprise_value |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pe | 1.00 | 0.33 | 0.24 | 0.42 | 0.49 | 0.20 | 0.12 | 0.04 | 0.11 | 0.02 | 0.03 | -0.01 | 0.01 | 0.02 | 0.04 | -0.02 | 0.00 | 0.00 | 0.01 | 0.05 | 0.08 | 0.07 |
| pb | 0.33 | 1.00 | 0.25 | 0.25 | 0.20 | 0.18 | 0.05 | 0.08 | 0.06 | -0.00 | 0.00 | -0.02 | 0.02 | -0.13 | -0.02 | 0.12 | -0.01 | -0.01 | 0.00 | 0.04 | 0.18 | 0.16 |
| ps | 0.24 | 0.25 | 1.00 | 0.34 | 0.27 | 0.18 | 0.05 | 0.04 | 0.12 | 0.60 | 0.59 | 0.00 | 0.02 | 0.12 | -0.02 | -0.03 | -0.00 | 0.03 | 0.02 | 0.04 | 0.09 | 0.09 |
| ev_ebitda | 0.42 | 0.25 | 0.34 | 1.00 | 0.61 | 0.23 | 0.09 | 0.05 | 0.11 | 0.04 | 0.04 | 0.03 | 0.03 | 0.04 | 0.52 | -0.02 | -0.01 | 0.02 | 0.06 | 0.05 | 0.08 | 0.08 |
| ev_ebit | 0.49 | 0.20 | 0.27 | 0.61 | 1.00 | 0.19 | 0.09 | 0.05 | 0.12 | 0.03 | 0.02 | 0.03 | 0.02 | 0.05 | 0.26 | -0.02 | -0.00 | -0.00 | 0.02 | 0.04 | 0.07 | 0.07 |
| ev_fcff | 0.20 | 0.18 | 0.18 | 0.23 | 0.19 | 1.00 | 0.06 | -0.00 | -0.01 | -0.01 | -0.01 | 0.06 | 0.00 | 0.01 | 0.02 | -0.02 | -0.00 | -0.01 | -0.01 | 0.06 | 0.13 | 0.12 |
| earn_yield | 0.12 | 0.05 | 0.05 | 0.09 | 0.09 | 0.06 | 1.00 | 0.07 | 0.15 | 0.04 | 0.06 | -0.01 | 0.30 | 0.05 | 0.00 | 0.00 | 0.03 | 0.05 | 0.05 | 0.04 | 0.03 | -0.02 |
| roe | 0.04 | 0.08 | 0.04 | 0.05 | 0.05 | -0.00 | 0.07 | 1.00 | 0.27 | 0.07 | 0.08 | 0.02 | 0.01 | 0.00 | -0.01 | 0.13 | -0.01 | 0.07 | 0.06 | 0.04 | -0.05 | -0.04 |
| roa | 0.11 | 0.06 | 0.12 | 0.11 | 0.12 | -0.01 | 0.15 | 0.27 | 1.00 | 0.27 | 0.29 | 0.06 | 0.05 | 0.06 | -0.05 | -0.01 | -0.08 | 0.20 | 0.20 | 0.14 | -0.12 | -0.10 |
| ebitda_margin | 0.02 | -0.00 | 0.60 | 0.04 | 0.03 | -0.01 | 0.04 | 0.07 | 0.27 | 1.00 | 0.93 | 0.02 | 0.02 | 0.10 | -0.03 | -0.01 | -0.01 | 0.08 | 0.06 | 0.05 | -0.04 | -0.04 |
| profit_margin | 0.03 | 0.00 | 0.59 | 0.04 | 0.02 | -0.01 | 0.06 | 0.08 | 0.29 | 0.93 | 1.00 | 0.02 | 0.02 | 0.11 | -0.02 | -0.01 | -0.00 | 0.06 | 0.05 | 0.05 | -0.04 | -0.03 |
| fcf | -0.01 | -0.02 | 0.00 | 0.03 | 0.03 | 0.06 | -0.01 | 0.02 | 0.06 | 0.02 | 0.02 | 1.00 | -0.00 | 0.02 | 0.01 | -0.01 | -0.01 | 0.02 | 0.02 | 0.06 | -0.21 | -0.26 |
| bvps | 0.01 | 0.02 | 0.02 | 0.03 | 0.02 | 0.00 | 0.30 | 0.01 | 0.05 | 0.02 | 0.02 | -0.00 | 1.00 | 0.01 | -0.01 | -0.01 | -0.00 | 0.00 | 0.01 | 0.02 | -0.07 | -0.08 |
| asset_turnover | 0.02 | -0.13 | 0.12 | 0.04 | 0.05 | 0.01 | 0.05 | 0.00 | 0.06 | 0.10 | 0.11 | 0.02 | 0.01 | 1.00 | 0.00 | 0.02 | 0.04 | 0.05 | 0.04 | 0.03 | -0.01 | -0.02 |
| debt_ebitda | 0.04 | -0.02 | -0.02 | 0.52 | 0.26 | 0.02 | 0.00 | -0.01 | -0.05 | -0.03 | -0.02 | 0.01 | -0.01 | 0.00 | 1.00 | 0.03 | 0.00 | -0.05 | -0.03 | -0.05 | 0.02 | 0.02 |
| leverage | -0.02 | 0.12 | -0.03 | -0.02 | -0.02 | -0.02 | 0.00 | 0.13 | -0.01 | -0.01 | -0.01 | -0.01 | -0.01 | 0.02 | 0.03 | 1.00 | 0.01 | -0.01 | -0.00 | -0.03 | 0.04 | -0.00 |
| rev_growth | 0.00 | -0.01 | -0.00 | -0.01 | -0.00 | -0.00 | 0.03 | -0.01 | -0.08 | -0.01 | -0.00 | -0.01 | -0.00 | 0.04 | 0.00 | 0.01 | 1.00 | 0.03 | 0.02 | -0.03 | 0.02 | 0.01 |
| ebitda_growth | 0.00 | -0.01 | 0.03 | 0.02 | -0.00 | -0.01 | 0.05 | 0.07 | 0.20 | 0.08 | 0.06 | 0.02 | 0.00 | 0.05 | -0.05 | -0.01 | 0.03 | 1.00 | 0.52 | 0.01 | -0.02 | -0.02 |
| ebit_growth | 0.01 | 0.00 | 0.02 | 0.06 | 0.02 | -0.01 | 0.05 | 0.06 | 0.20 | 0.06 | 0.05 | 0.02 | 0.01 | 0.04 | -0.03 | -0.00 | 0.02 | 0.52 | 1.00 | 0.00 | -0.03 | -0.02 |
| div_yield | 0.05 | 0.04 | 0.04 | 0.05 | 0.04 | 0.06 | 0.04 | 0.04 | 0.14 | 0.05 | 0.05 | 0.06 | 0.02 | 0.03 | -0.05 | -0.03 | -0.03 | 0.01 | 0.00 | 1.00 | -0.08 | -0.08 |
| market_cap | 0.08 | 0.18 | 0.09 | 0.08 | 0.07 | 0.13 | 0.03 | -0.05 | -0.12 | -0.04 | -0.04 | -0.21 | -0.07 | -0.01 | 0.02 | 0.04 | 0.02 | -0.02 | -0.03 | -0.08 | 1.00 | 0.78 |
| enterprise_value | 0.07 | 0.16 | 0.09 | 0.08 | 0.07 | 0.12 | -0.02 | -0.04 | -0.10 | -0.04 | -0.03 | -0.26 | -0.08 | -0.02 | 0.02 | -0.00 | 0.01 | -0.02 | -0.02 | -0.08 | 0.78 | 1.00 |

## Most correlated pairs

| factor A | factor B | corr |
|---|---|---|
| ebitda_margin | profit_margin | 0.931 |
| market_cap | enterprise_value | 0.780 |
| ev_ebitda | ev_ebit | 0.610 |
| ps | ebitda_margin | 0.602 |
| ps | profit_margin | 0.593 |
| ev_ebitda | debt_ebitda | 0.524 |
| ebitda_growth | ebit_growth | 0.517 |
| pe | ev_ebit | 0.490 |
| pe | ev_ebitda | 0.423 |
| ps | ev_ebitda | 0.342 |

## Least correlated pairs (|corr| smallest)

| factor A | factor B | corr |
|---|---|---|
| earn_yield | leverage | 0.001 |
| pb | ebitda_margin | -0.001 |
| profit_margin | rev_growth | -0.001 |
| ebit_growth | div_yield | 0.001 |
| leverage | ebit_growth | -0.001 |
| pb | ebit_growth | 0.001 |
| leverage | enterprise_value | -0.002 |
| ev_ebit | rev_growth | -0.002 |
| ev_fcff | rev_growth | -0.003 |
| fcf | bvps | -0.003 |

## PCA eigenvalues (on the date-averaged correlation matrix)

| PC | eigenvalue | explained | cumulative |
|---|---|---|---|
| PC1 | 3.014 | 13.7% | 13.7% |
| PC2 | 2.415 | 11.0% | 24.7% |
| PC3 | 1.883 | 8.6% | 33.2% |
| PC4 | 1.591 | 7.2% | 40.5% |
| PC5 | 1.322 | 6.0% | 46.5% |
| PC6 | 1.236 | 5.6% | 52.1% |
| PC7 | 1.165 | 5.3% | 57.4% |
| PC8 | 1.054 | 4.8% | 62.2% |
| PC9 | 1.022 | 4.6% | 66.8% |
| PC10 | 0.944 | 4.3% | 71.1% |
| PC11 | 0.912 | 4.1% | 75.3% |
| PC12 | 0.879 | 4.0% | 79.3% |
| PC13 | 0.772 | 3.5% | 82.8% |
| PC14 | 0.701 | 3.2% | 86.0% |
| PC15 | 0.631 | 2.9% | 88.8% |
| PC16 | 0.621 | 2.8% | 91.6% |
| PC17 | 0.486 | 2.2% | 93.9% |
| PC18 | 0.474 | 2.2% | 96.0% |
| PC19 | 0.364 | 1.7% | 97.7% |
| PC20 | 0.232 | 1.1% | 98.7% |
| PC21 | 0.214 | 1.0% | 99.7% |
| PC22 | 0.067 | 0.3% | 100.0% |

Effective dimensionality: **9** components with eigenvalue > 1 (Kaiser); **13** PCs for 80% of variance, **16** for 90%.

## Component interpretations (top loadings)

**PC1** (13.7% of variance): negatively on ps (-0.75), ev_ebitda (-0.64), profit_margin (-0.61).
**PC2** (11.0% of variance): loads positively on profit_margin (+0.60), ebitda_margin (+0.60); negatively on market_cap (-0.55), enterprise_value (-0.54), ev_ebitda (-0.42).
**PC3** (8.6% of variance): loads positively on fcf (+0.39), ev_ebitda (+0.36); negatively on enterprise_value (-0.65), market_cap (-0.63), ebitda_margin (-0.37).
**PC4** (7.2% of variance): loads positively on ebitda_growth (+0.72), ebit_growth (+0.72), roa (+0.31).
**PC5** (6.0% of variance): loads positively on bvps (+0.48), earn_yield (+0.47), pb (+0.35); negatively on debt_ebitda (-0.48), ebit_growth (-0.31), ebitda_growth (-0.29).

## Loadings, first 5 PCs

| factor | PC1 | PC2 | PC3 | PC4 | PC5 |
|---|---|---|---|---|---|
| pe | -0.54 | -0.35 | 0.24 | 0.00 | 0.15 |
| pb | -0.39 | -0.34 | -0.02 | 0.09 | 0.35 |
| ps | -0.75 | 0.17 | -0.26 | -0.21 | -0.01 |
| ev_ebitda | -0.64 | -0.42 | 0.36 | -0.10 | -0.25 |
| ev_ebit | -0.59 | -0.39 | 0.34 | -0.08 | -0.11 |
| ev_fcff | -0.31 | -0.29 | 0.03 | -0.02 | 0.16 |
| earn_yield | -0.22 | 0.03 | 0.16 | 0.21 | 0.47 |
| roe | -0.18 | 0.14 | 0.14 | 0.26 | 0.24 |
| roa | -0.39 | 0.37 | 0.19 | 0.31 | 0.14 |
| ebitda_margin | -0.61 | 0.60 | -0.37 | -0.19 | -0.08 |
| profit_margin | -0.61 | 0.60 | -0.37 | -0.19 | -0.06 |
| fcf | -0.02 | 0.20 | 0.39 | -0.15 | -0.02 |
| bvps | -0.08 | 0.08 | 0.18 | 0.07 | 0.48 |
| asset_turnover | -0.14 | 0.15 | -0.01 | 0.01 | -0.18 |
| debt_ebitda | -0.21 | -0.31 | 0.29 | -0.20 | -0.48 |
| leverage | 0.00 | -0.04 | -0.02 | 0.10 | 0.14 |
| rev_growth | 0.01 | -0.03 | -0.04 | 0.04 | -0.10 |
| ebitda_growth | -0.14 | 0.23 | 0.10 | 0.72 | -0.29 |
| ebit_growth | -0.16 | 0.20 | 0.14 | 0.72 | -0.31 |
| div_yield | -0.13 | 0.12 | 0.17 | -0.01 | 0.25 |
| market_cap | -0.15 | -0.55 | -0.63 | 0.25 | 0.02 |
| enterprise_value | -0.15 | -0.54 | -0.65 | 0.26 | -0.02 |

## Redundancy clusters (|corr| ≥ 0.70)

- **ebitda_margin, profit_margin** — max |corr| 0.93; keep **profit_margin**, drop/merge ebitda_margin.
- **enterprise_value, market_cap** — max |corr| 0.78; keep **enterprise_value**, drop/merge market_cap.

## Key takeaways
- Highest factor overlap: ebitda_margin × profit_margin (corr +0.931) — these two carry almost the same information and should not both earn full weight.
- Of 22 factors, 9 principal components exceed eigenvalue 1 and 13 explain 80% of the variance: the effective dimensionality of the factor set is roughly 13, not 22.
- Redundancy recommendation: consolidate 2 near-duplicate factors (ebitda_margin, market_cap) into their cluster keepers before assigning composite weights — otherwise the composite double-counts the same underlying exposure.
- PC1 alone explains 13.7% of factor variance — check its interpretation above: if it is a quality axis, the composite's quality sleeve is implicitly overweight through factor multiplicity, not through its stated weight.

## Analyst recommendation — composite weights (authored 2026-09-28)

Current `config/factors.yaml`: value 0.35 / quality 0.25 / growth 0.15 /
momentum 0.15 / lowvol 0.10. Proposed: **value 0.20 / quality 0.40 /
growth 0.05 / momentum 0.20 / lowvol 0.15**, plus factor-level changes:

1. **Cut the value sleeve nearly in half (0.35 → 0.20).** It is the largest
   sleeve yet its components are individually weak (pe t=0.65, ev_ebitda
   t=1.08, ev_ebit t=0.87, ps t=2.37 — all |t|<2.5) *and* mutually correlated
   (0.33–0.61), so the sleeve is overweight through multiplicity, not merit.
   Consolidate its six multiples to two: **earn_yield** (t=3.92, the best of
   the family) and **ev_ebitda**. Note pe × earn_yield is only +0.12: pe
   quarantines loss-makers to NaN while earn_yield keeps them as negative
   yield — they are *different* signals, and earn_yield's is the better one.
2. **Raise quality (0.25 → 0.40).** roe (t=6.41), roa (t=5.45), asset_turnover
   (t=5.71) are the three strongest signals in the lab, and roe × roa is only
   +0.27 — the sleeve's diversification is genuine, not double-counting.
3. **Starve growth (0.15 → 0.05).** All growth ICs have |t|<1, the growth
   factors are mutually uncorrelated noise, and PC4 shows growth is its own
   isolated axis — it diversifies the composite but predicts nothing. Keep a
   toe-hold, not a sleeve.
4. **Drop the two redundant factors** (ebitda_margin → profit_margin,
   market_cap → enterprise_value) per the clusters above.
5. **Fix the size orientation.** market_cap/enterprise_value ICs are
   significantly *negative* (t=−4.3/−5.4): the composite's small-cap tilt
   fights a six-year mega-cap headwind. Either flip the orientation for this
   regime or drop size until the premium reappears — do not keep a
   negatively-oriented factor at full weight.
6. **PC1 warning for sleeve arithmetic:** value and profitability load on the
   *same* first principal axis, so the value and quality sleeves are not
   independent bets — summing their weights overstates true diversification.

Momentum/lowvol sleeves were not tested here (no momentum or beta factors in
the panel); their weights are carried over, not endorsed.

## Caveats
- Contemporaneous factor structure, not prediction: no lookahead issue exists here by construction (nothing at t is joined to information from after t).
- 37% of panel rows have sector 'unknown' (kept as its own neutralization bucket, not dropped).
- Fundamentals cover ~5,880 of 22,569 tickers; small caps are largely price-only, so factor z-scores are NaN for them and pairwise-complete correlations lean on covered names.
- Restated fundamental vintages embed later revisions (values, not availability) — inherited from the panel.
- Average correlations smooth over regime changes; a single 2020-2026 mean can hide time-varying structure (e.g. the 2022 rate shock).
