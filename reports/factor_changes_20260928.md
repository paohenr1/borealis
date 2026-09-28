# Factor-universe changes — before/after (2026-09-28)

Companion to `factor_efficacy_20260928.md` and `factor_correlation_pca_20260928.md`. The lab's scored set went from 22 factors to 15: value sleeve consolidated to earn_yield + ev_ebitda; ebitda_margin and market_cap dropped as near-duplicates; enterprise_value orientation flipped to ride the 2020-2026 mega-cap regime (regime-dependent; flip-back rule in `preprocess.py`). Original reports untouched.

## Per-factor before → after (21-day horizon)

| factor | IC old | t old | spread old | IC new | t new | spread new |
|---|---|---|---|---|---|---|
| asset_turnover | +0.0415 | +5.71 | +1.39% | +0.0415 | +5.71 | +1.39% |
| bvps | +0.0418 | +5.37 | +0.66% | +0.0418 | +5.37 | +0.66% |
| debt_ebitda | -0.0526 | -6.14 | -0.74% | -0.0526 | -6.14 | -0.74% |
| div_yield | +0.0524 | +5.12 | +0.91% | +0.0524 | +5.12 | +0.91% |
| earn_yield | +0.0370 | +3.92 | +1.06% | +0.0370 | +3.92 | +1.06% |
| ebit_growth | +0.0092 | +1.59 | +0.36% | +0.0092 | +1.59 | +0.36% |
| ebitda_growth | +0.0051 | +0.90 | +0.29% | +0.0051 | +0.90 | +0.29% |
| enterprise_value | -0.0593 | -5.43 | -0.46% | +0.0593 | +5.43 | +0.46% |
| ev_ebitda | +0.0117 | +1.08 | +0.39% | +0.0117 | +1.08 | +0.39% |
| fcf | +0.0305 | +3.44 | +0.30% | +0.0305 | +3.44 | +0.30% |
| leverage | -0.0350 | -4.67 | -0.37% | -0.0350 | -4.67 | -0.37% |
| profit_margin | +0.0312 | +3.19 | +0.71% | +0.0312 | +3.19 | +0.71% |
| rev_growth | -0.0017 | -0.29 | -0.15% | -0.0017 | -0.29 | -0.15% |
| roa | +0.0635 | +5.45 | +0.91% | +0.0635 | +5.45 | +0.91% |
| roe | +0.0647 | +6.41 | +1.26% | +0.0647 | +6.41 | +1.26% |

Only enterprise_value changed by construction (sign flip); all other kept factors are numerically identical, confirming the rerun is apples-to-apples.

## Dropped factors (old stats — dead weight removed)

| factor | IC | t-stat | reason |
|---|---|---|---|
| ebitda_margin | +0.0250 | +2.72 | near-duplicate of profit_margin (+0.931) |
| ev_ebit | +0.0089 | +0.87 | value consolidation |
| ev_fcff | -0.0033 | -0.37 | value consolidation |
| market_cap | -0.0430 | -4.33 | near-duplicate of enterprise_value (+0.780) |
| pb | +0.0130 | +1.23 | value consolidation |
| pe | +0.0064 | +0.65 | value consolidation |
| ps | +0.0256 | +2.37 | value consolidation |

## Aggregate efficacy

- Mean |IC| (21d): old 22-factor set 0.0301 → new 15-factor set 0.0358.
- Mean |t-stat|: 3.24 → 3.91.
- The cut removed the weakest tail (all dropped value multiples had |t| < 2.5) and one negatively-oriented size factor; the kept set is denser in signal.

## Composite implications (sleeve-weighted, value/quality/growth only)

- Momentum/lowvol have no panel proxies, so both composites use only the three present sleeves, renormalized to sum to 1.
- Old composite (0.35/0.25/0.15 → renormalized): IC +0.0365, t +4.75, hit rate 70%.
- New composite (0.20/0.40/0.05 → renormalized): IC +0.0455, t +6.06, hit rate 75%.
- Read: the composite now leans on the three strongest, genuinely uncorrelated quality signals (roe × roa only +0.27) instead of spreading weight across six mutually-correlated weak value multiples; growth is a 5% toe-hold, not a bet.

## Judgment calls

- Composite excludes momentum/lowvol (no panel proxies) — the factors.yaml weights for those sleeves are carried over, not validated here.
- div_yield (t=+5.12) has no workbook sleeve; it is scored in the lab but absent from the composite — a yield sleeve is an open design question.
- enterprise_value flip is regime-dependent by construction; monitor trailing-12m size IC for the flip-back signal.

## Remaining concerns for a hiring manager

- 37% of rows still sit in the 'unknown' sector bucket; sector neutralization is weakest exactly where coverage is thinnest.
- Fundamentals cover ~5,880 of 22,569 tickers: the lab's verdicts are large/mid-cap verdicts, and small caps are price-only.
- Restated fundamental vintages embed later revisions (values, not availability) — availability discipline holds, value purity does not.
- Average 2020-2026 correlations smooth over regime changes (e.g. the 2022 rate shock); the size flip especially should be re-checked out-of-sample.
