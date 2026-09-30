"""Lab preprocessing: orient factors (higher = better), quarantine, z-score.

Conventions inherited from the scoring engine (``borealis.scoring.composite``):
winsorize at +/-3 sigma within the neutralization group, then z-score.
Unknown-sector handling: "unknown" is kept as its own neutralization bucket
rather than dropped. Rationale: 37% of panel rows lack sector metadata and
dropping them would bias the sample toward large, metadata-covered names;
bucketing keeps the full cross-section while still removing the average
"unknown" effect, and it matches what ``composite_score`` already does.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from borealis.scoring.composite import winsorize

# Factor -> direction so that HIGHER oriented value = more attractive.
# Value ratios: cheap (low) = good -> -1. Profitability, growth, yield,
# efficiency: high = good -> +1.
#
# Universe changes 2026-09-28 (lab reports factor_efficacy_20260928.md,
# factor_correlation_pca_20260928.md):
#  - Value sleeve consolidated to earn_yield + ev_ebitda (the six-multiple
#    sleeve was weak and mutually correlated; earn_yield t=3.92 was the best
#    of the family).
#  - ebitda_margin dropped (keep profit_margin, |corr| +0.931);
#    market_cap dropped (keep enterprise_value, |corr| +0.780).
FACTOR_DIRECTION: dict[str, int] = {
    "ev_ebitda": -1,
    # Live value sleeve (2026-09-30): earnings yield, P/S, EV/EBITDA, P/B.
    # P/E was replaced by earnings yield (decision 2026-09-30): EY = 1/P/E,
    # same economic information, but P/E explodes near zero earnings and
    # poisons the winsorize/z-score pipeline. pe stays scored individually
    # as a diagnostic.
    "earn_yield": 1, "pe": -1, "ps": -1, "pb": -1,
    "roe": 1, "roa": 1, "profit_margin": 1,
    # Exact live quality metrics (added 2026-09-30): gross_margin from the
    # INDU calculations template (NaN for financials, sector-imputed like
    # the live path), fcf_margin = fcf / TTM revenue (panel-derived, same
    # formula as universe_live.py), debt_to_equity (lower = better).
    "gross_margin": 1, "fcf_margin": 1, "debt_to_equity": -1,
    "fcf": 1, "bvps": 1, "asset_turnover": 1,
    "debt_ebitda": -1, "leverage": -1,
    "rev_growth": 1, "ebitda_growth": 1, "ebit_growth": 1,
    "div_yield": 1,
    # Financial health (added 2026-09-30): interest coverage = EBIT /
    # interest expense. Higher = better (more comfortably services debt).
    # Distinct from debt_ebitda/leverage (how much debt) -- this is whether
    # earnings cover its cost.
    "interest_coverage": 1,
    # REGIME-DEPENDENT (flipped 2026-09-28): enterprise_value ICs were
    # significantly negative (t~-5.4) over 2020-2026 -- large caps
    # outperformed, so larger = more attractive for now. Flip back to -1 if
    # the small-cap premium reappears, i.e. size IC turns positive over a
    # trailing 12-month window.
    "enterprise_value": 1,
    # Price-derived proxies (lab/price_proxies.py; validated 2026-09-28).
    # mom_12m1m: 12-month trailing total return skipping the most recent
    #   month (standard 12-1) -- higher = more attractive.
    # vol_126d: 126-trading-day annualized std of daily total returns --
    #   lower = more attractive. Winsorized at +/-3 sigma like all factors;
    #   sector-neutral z-scoring keeps the comparison within sectors.
    #   The LIVE low-vol definition since the 2026-09-30 sleeve decisions.
    # beta_252d (added 2026-09-30): 252-day beta vs SPY -- lower = more
    #   attractive. Was the live low-vol definition until the 2026-09-30
    #   decisions; rejected on both universes, now scored as a diagnostic.
    "mom_12m1m": 1,
    "vol_126d": -1,
    "beta_252d": -1,
}

# Factors cut from the scored set 2026-09-28; kept out of composites/reports.
# Rationale in one line each:
# ev_ebit/ev_fcff: value-sleeve consolidation to earn_yield+ev_ebitda.
# ebitda_margin: near-duplicate of profit_margin (|corr| +0.931).
# market_cap: near-duplicate of enterprise_value (|corr| +0.780).
# NOTE 2026-09-30: pe/pb/ps were reinstated for the live value sleeve on
# 2026-09-30-morning (P/E + P/S + EV/EBITDA + P/B); that afternoon Henry
# decided to replace P/E with earnings yield (same information, better
# behaved in the z-score pipeline). pe stays scored as a diagnostic.
DROPPED_FACTORS: frozenset[str] = frozenset(
    {"ev_ebit", "ev_fcff", "ebitda_margin", "market_cap"}
)

# Ratios where a zero/negative value means missing or negative earnings.
# Quarantined to NaN (never ranked as "cheapest"), per factors/value.py.
# Note: earn_yield is deliberately NOT quarantined -- a negative earnings
# yield is informative (unlike a negative P/E ratio), which is why it beats
# pe as a value signal.
QUARANTINE_NONPOSITIVE = frozenset({"ev_ebitda", "pe", "ps", "pb"})

# Sleeve -> member factors for the lab composite.
# Realigned 2026-09-30 to Henry's five sleeve decisions:
# - value: P/E replaced by earnings yield (1/P/E, same economic information;
#   P/E explodes near zero earnings and poisons the winsorize/z-score
#   pipeline; EY is bounded and well-behaved). pe stays scored individually
#   as a diagnostic.
# - quality: EXACT live 8-metric sleeve (2026-09-30 panel extension):
#   roe, roa, gross_margin, profit_margin, fcf_margin (= fcf / revenue),
#   debt_to_equity, debt_ebitda, interest_coverage. Raw fcf / leverage
#   remain scored individually as diagnostics. bvps/asset_turnover removed
#   -- not in the live model. Weight 0.00 (decision 2026-09-30): scored
#   every run as a diagnostic with a reinstatement rule (see
#   factors/quality.py).
# - lowvol: vol_126d = 126-day realized volatility (decision 2026-09-30).
#   beta_252d stays individually scored as a diagnostic; it was rejected on
#   both universes (broad -9.35%/yr, large-cap -7.8%/yr, worst exactly when
#   low-vol should protect).
# - size: weight 0.00 (decision 2026-09-30); the flip-back rule
#   (trailing-12m size IC positive -> smaller-is-better; annual review) is
#   its reinstatement path.
# - yield: standalone sleeve (div_yield); not in the live composite.
SLEEVES: dict[str, list[str]] = {
    "value": ["earn_yield", "ps", "ev_ebitda", "pb"],
    "quality": ["roe", "roa", "gross_margin", "profit_margin", "fcf_margin",
                "debt_to_equity", "debt_ebitda", "interest_coverage"],
    "growth": ["rev_growth", "ebitda_growth", "ebit_growth"],
    "yield": ["div_yield"],
    "momentum": ["mom_12m1m"],
    "lowvol": ["vol_126d"],
    "size": ["enterprise_value"],
}

UNKNOWN_SECTOR = "unknown"


def oriented_factor(df: pd.DataFrame, col: str) -> pd.Series:
    """Raw factor oriented so higher = more attractive, with quarantine."""
    if col not in FACTOR_DIRECTION:
        raise KeyError(f"no direction defined for factor {col!r}")
    s = pd.to_numeric(df[col], errors="coerce").astype(float)
    if col in QUARANTINE_NONPOSITIVE:
        s = s.where(s > 0, np.nan)
    return (s * FACTOR_DIRECTION[col]).rename(f"oriented_{col}")


def zscore_by_date_sector(df: pd.DataFrame, col: str,
                          sector_col: str = "sector",
                          sigma: float = 3.0) -> pd.Series:
    """Sector-neutral z-score per date: winsorize then z-score within
    (date, sector). The "unknown" sector is its own bucket (see module doc)."""
    keys = [df["date"], df[sector_col]]
    w = df.groupby(keys, observed=True)[col].transform(
        lambda s: winsorize(s, sigma))
    mu = w.groupby(keys, observed=True).transform("mean")
    sd = w.groupby(keys, observed=True).transform("std").replace(0, np.nan)
    return ((w - mu) / sd).rename(f"z_{col}")


def add_lab_zscores(df: pd.DataFrame, factors: list[str],
                    sector_col: str = "sector",
                    sigma: float = 3.0) -> pd.DataFrame:
    """Return df plus ``z_<factor>`` columns: oriented, quarantined,
    sector-neutral z-scores computed cross-sectionally per date."""
    out = df.copy()
    for col in factors:
        out[f"oriented_{col}"] = oriented_factor(out, col)
        out[f"z_{col}"] = zscore_by_date_sector(out, f"oriented_{col}",
                                                sector_col, sigma)
    return out


def available_factors(panel_columns: list[str]) -> list[str]:
    """Factor columns (from FACTOR_DIRECTION) actually present in the panel."""
    return [c for c in FACTOR_DIRECTION if c in panel_columns]
