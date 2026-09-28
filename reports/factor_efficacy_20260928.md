# Borealis Factor-Efficacy Lab

_Generated 2026-09-28T15:56:43+00:00 · panel data/processed/intrinio/panel · 81 monthly rebalance dates (2020-01-31 → 2026-09-25)_

## Sampling scheme
- Rebalance dates: month-end trading days in the panel (81 dates, 2020-01-31 to 2026-09-25).
- Factors oriented (higher = more attractive), zero/negative value ratios quarantined, winsorized at ±3σ and z-scored within (date, sector); 'unknown' sector kept as its own bucket.
- IC: Spearman rank correlation of z(t) vs forward total return after t; 21-trading-day primary, 63-day secondary.
- Quintiles: per-date sort on z into 5 equal groups; spread = equal-weighted Q5 − Q1 forward return, with forward returns winsorized per date at the 1st/99th percentiles (micro-cap lottery tickets would otherwise dominate equal-weighted means).
- Half-life: semi-annual base dates (11), rank autocorrelation of z-score ranks at trading-day lags [5, 21, 42, 63, 126, 189, 252]; first crossing of 0.5, interpolated.
- Point-in-time discipline inherited from the panel; z(t) only meets returns after t.

## Information coefficients (rank IC, sector-neutral z vs forward total return)

| factor | IC₂₁ mean | IC₂₁ t-stat | IC₂₁ hit rate | IC₆₃ mean | IC₆₃ t-stat | IC₆₃ hit rate | N |
|---|---|---|---|---|---|---|---|
| pe | 0.0064 | 0.65 | 56.96% | 0.0065 | 0.59 | 50.65% | 79 |
| pb | 0.0130 | 1.23 | 54.43% | 0.0226 | 1.99 | 61.04% | 79 |
| ps | 0.0256 | 2.37 | 55.70% | 0.0505 | 4.00 | 63.64% | 79 |
| ev_ebitda | 0.0117 | 1.08 | 56.96% | 0.0206 | 1.92 | 59.74% | 79 |
| ev_ebit | 0.0089 | 0.87 | 56.96% | 0.0167 | 1.79 | 53.25% | 79 |
| ev_fcff | -0.0033 | -0.37 | 46.84% | 0.0023 | 0.26 | 51.95% | 79 |
| earn_yield | 0.0370 | 3.92 | 67.09% | 0.0529 | 5.88 | 77.92% | 79 |
| roe | 0.0647 | 6.41 | 75.95% | 0.0818 | 7.89 | 88.31% | 79 |
| roa | 0.0635 | 5.45 | 70.89% | 0.0781 | 6.64 | 85.71% | 79 |
| ebitda_margin | 0.0250 | 2.72 | 60.76% | 0.0304 | 2.85 | 64.94% | 79 |
| profit_margin | 0.0312 | 3.19 | 58.23% | 0.0410 | 3.54 | 64.94% | 79 |
| fcf | 0.0305 | 3.44 | 64.56% | 0.0323 | 3.48 | 64.94% | 79 |
| bvps | 0.0418 | 5.37 | 70.89% | 0.0589 | 5.67 | 77.92% | 79 |
| asset_turnover | 0.0415 | 5.71 | 72.15% | 0.0561 | 8.23 | 83.12% | 79 |
| debt_ebitda | -0.0526 | -6.14 | 24.05% | -0.0755 | -8.90 | 14.29% | 79 |
| leverage | -0.0350 | -4.67 | 26.58% | -0.0518 | -6.81 | 14.29% | 79 |
| rev_growth | -0.0017 | -0.29 | 48.10% | 0.0006 | 0.08 | 55.84% | 79 |
| ebitda_growth | 0.0051 | 0.90 | 60.76% | 0.0069 | 1.14 | 66.23% | 79 |
| ebit_growth | 0.0092 | 1.59 | 62.03% | 0.0115 | 1.82 | 63.64% | 79 |
| div_yield | 0.0524 | 5.12 | 73.42% | 0.0693 | 6.59 | 77.92% | 79 |
| market_cap | -0.0430 | -4.33 | 30.38% | -0.0529 | -5.42 | 22.08% | 79 |
| enterprise_value | -0.0593 | -5.43 | 27.85% | -0.0840 | -7.19 | 18.18% | 79 |

## Quintile spreads (Q5 − Q1, equal-weighted, monthly %)

| factor | spread₂₁ mean | spread₂₁ t-stat | spread₂₁ hit rate | Q1₂₁ | Q5₂₁ | spread₆₃ mean | spread₆₃ t-stat | cumulative₂₁ |
|---|---|---|---|---|---|---|---|---|
| pe | 0.41% | 1.63 | 62.03% | 0.99% | 1.40% | 1.18% | 2.38 | 32.1% |
| pb | 0.36% | 0.93 | 50.63% | 0.75% | 1.11% | 0.99% | 1.35 | 28.4% |
| ps | 0.92% | 2.34 | 56.96% | 0.22% | 1.13% | 2.92% | 3.69 | 72.3% |
| ev_ebitda | 0.39% | 1.28 | 59.49% | 1.10% | 1.50% | 1.37% | 2.56 | 31.0% |
| ev_ebit | 0.34% | 1.21 | 54.43% | 0.97% | 1.32% | 1.14% | 2.52 | 27.1% |
| ev_fcff | 0.44% | 1.52 | 54.43% | 1.09% | 1.53% | 1.53% | 2.70 | 34.9% |
| earn_yield | 1.06% | 3.30 | 67.53% | 0.21% | 1.27% | 2.82% | 4.84 | 81.2% |
| roe | 1.26% | 2.63 | 68.35% | 0.03% | 1.29% | 2.35% | 2.39 | 99.8% |
| roa | 0.91% | 1.33 | 55.70% | 0.25% | 1.16% | 1.12% | 0.75 | 72.2% |
| ebitda_margin | 0.53% | 1.13 | 53.16% | 0.61% | 1.14% | 0.65% | 0.61 | 42.2% |
| profit_margin | 0.71% | 1.34 | 55.70% | 0.50% | 1.21% | 0.99% | 0.76 | 56.2% |
| fcf | 0.30% | 0.91 | 56.96% | 1.22% | 1.52% | 0.36% | 0.64 | 23.7% |
| bvps | 0.66% | 1.81 | 63.29% | 0.55% | 1.21% | 1.32% | 1.37 | 52.3% |
| asset_turnover | 1.39% | 3.57 | 67.09% | -0.02% | 1.37% | 2.90% | 3.87 | 110.0% |
| debt_ebitda | -0.74% | -1.99 | 40.51% | 1.28% | 0.54% | -1.43% | -1.82 | -58.8% |
| leverage | -0.37% | -1.13 | 45.57% | 1.30% | 0.92% | -1.15% | -1.89 | -29.5% |
| rev_growth | -0.15% | -0.70 | 50.63% | 0.86% | 0.72% | -0.28% | -0.61 | -11.7% |
| ebitda_growth | 0.29% | 1.18 | 59.49% | 1.01% | 1.30% | 1.24% | 3.22 | 22.9% |
| ebit_growth | 0.36% | 1.44 | 59.49% | 0.94% | 1.31% | 0.99% | 2.39 | 28.7% |
| div_yield | 0.91% | 1.97 | 52.94% | -0.38% | 0.53% | 2.39% | 3.13 | 46.3% |
| market_cap | 0.02% | 0.06 | 41.77% | 1.20% | 1.22% | 0.62% | 0.78 | 1.7% |
| enterprise_value | -0.46% | -0.90 | 45.57% | 1.24% | 0.78% | -0.92% | -0.81 | -36.2% |

## Signal half-life (trading days; rank autocorrelation decay to 0.5)

| factor | half-life (d) | L5 | L21 | L42 | L63 | L126 | L189 | L252 |
|---|---|---|---|---|---|---|---|---|
| pe | 183 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| pb | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| ps | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| ev_ebitda | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| ev_ebit | 230 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| ev_fcff | 146 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| earn_yield | 239 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| roe | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| roa | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| ebitda_margin | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| profit_margin | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| fcf | 158 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| bvps | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| asset_turnover | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| debt_ebitda | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| leverage | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| rev_growth | 90 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| ebitda_growth | 103 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| ebit_growth | 98 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| div_yield | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| market_cap | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| enterprise_value | >252 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Annual quintile spreads, 21-day horizon (monthly %)

| factor | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| pe | -0.22% | 0.73% | 0.87% | 0.95% | -0.83% | 0.72% | 0.78% |
| pb | -1.12% | 2.23% | 1.11% | 0.04% | -0.40% | 0.09% | 0.73% |
| ps | -0.53% | 2.76% | 2.17% | 0.84% | -0.13% | 0.80% | 0.22% |
| ev_ebitda | -1.68% | 1.32% | 1.20% | 0.65% | -0.36% | 1.12% | 0.58% |
| ev_ebit | -1.13% | 1.29% | 0.70% | 1.12% | -0.58% | 0.76% | 0.18% |
| ev_fcff | 0.46% | 0.61% | 1.00% | 0.12% | -0.39% | 1.11% | -0.00% |
| earn_yield | -0.36% | 1.57% | 1.60% | 1.60% | 1.45% | 0.92% | -0.01% |
| roe | -2.26% | 1.70% | 1.53% | 2.95% | 1.00% | 1.76% | 2.79% |
| roa | -5.72% | 2.10% | 1.71% | 2.71% | 1.02% | 2.33% | 3.21% |
| ebitda_margin | -4.42% | 1.54% | 1.68% | 0.93% | 0.09% | 1.74% | 3.37% |
| profit_margin | -4.65% | 1.40% | 2.38% | 1.08% | 0.36% | 2.63% | 2.55% |
| fcf | -0.74% | 0.33% | -0.14% | 1.36% | 0.32% | 0.47% | 0.65% |
| bvps | -2.88% | 2.85% | 0.41% | 1.33% | 0.59% | 0.89% | 2.00% |
| asset_turnover | -0.69% | 1.23% | 1.51% | 2.92% | 1.93% | 0.75% | 2.59% |
| debt_ebitda | 1.87% | -2.40% | -1.04% | -0.89% | -0.93% | -0.13% | -2.39% |
| leverage | 1.63% | -2.21% | -0.77% | -0.24% | -0.05% | -0.33% | -0.83% |
| rev_growth | -0.17% | -1.10% | -1.33% | 0.09% | 0.53% | 0.69% | 0.54% |
| ebitda_growth | 0.05% | -0.20% | 0.58% | 0.65% | 0.62% | 0.01% | 0.33% |
| ebit_growth | 0.11% | -0.11% | 0.35% | 0.80% | 0.62% | 0.05% | 0.96% |
| div_yield | n/a | 1.81% | -0.09% | 1.05% | -1.06% | 1.71% | 2.11% |
| market_cap | 1.83% | 0.07% | 0.05% | -0.84% | -0.31% | -0.15% | -0.86% |
| enterprise_value | 3.86% | -2.53% | -0.68% | -1.66% | -1.14% | -0.15% | -1.23% |

## Key takeaways
- Strongest signals (by 21-day IC t-stat): roe (t=6.41, IC=+0.0647, Q5−Q1=+1.26%/mo, half-life≈>252d); asset_turnover (t=5.71, IC=+0.0415, Q5−Q1=+1.39%/mo, half-life≈>252d); roa (t=5.45, IC=+0.0635, Q5−Q1=+0.91%/mo, half-life≈>252d).
- Indistinguishable from noise (|t| < 2): ebit_growth, pb, ev_ebitda, ebitda_growth, ev_ebit ….
- Significantly *negative* IC (signal runs opposite to its orientation — consider flipping or dropping): market_cap, leverage, enterprise_value, debt_ebitda.
- Slowest-decaying signals (rebalance least often): pb (>252d), ps (>252d).

## Caveats
- 37% of panel rows have sector 'unknown' (kept as its own neutralization bucket, not dropped).
- Fundamentals cover ~5,880 of 22,569 tickers; small caps are largely price-only, so factor z-scores are NaN for them.
- Restated fundamental vintages embed later revisions (values, not availability).
- Panel returns are total returns (split/dividend-adjusted); dividends are not modeled separately.
- Forward-return horizons truncate the sample end (63d IC uses fewer recent dates).
