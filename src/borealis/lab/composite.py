"""Sleeve-weighted composite score for the lab.

Composite z per (date, ticker) = sum over sleeves of
weight_sleeve * mean(z of available sleeve members).
Sleeve means are pairwise-complete: a ticker missing one metric still gets
a sleeve score from the rest -- dropping tickers on any single missing
metric would shrink the cross-section toward fully-covered large caps.
Sleeve weight mass is renormalized across the sleeves actually present for
each ticker (e.g. momentum is NaN for the first ~13 months of the panel,
so early composites lean on the other sleeves).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from borealis.lab.preprocess import SLEEVES

# (Historical note: weights revised 2026-09-28 after the momentum/lowvol
# validation; see reports/factor_momentum_lowvol_20260928.md. Superseded
# by the 2026-09-30 sleeve decisions below.)
# Live composite weights (Henry's five sleeve decisions, 2026-09-30).
# Raw: value .20, momentum .20, lowvol(126d) .10, quality .00, size .00,
# growth .00. Per-ticker renormalization of available nonzero weights
# makes the effective mix 0.40/0.40/0.20 (value/momentum/lowvol) for a
# fully-covered ticker.
# quality 0.00 = scored every run as a diagnostic with a reinstatement
#   rule (see factors/quality.py); dead on large caps (IC~0, all 8 metrics
#   t<1.3) despite broad-panel validation.
# size 0.00 = scored every run; the flip-back rule (trailing-12m size IC
#   positive in the academic orientation -> smaller-is-better; annual
#   review) is its reinstatement path. Failed natively on large caps.
# growth 0.00 = FALSIFIED BELIEF (2026-09-30): widely believed to drive
#   returns, tested and rejected; scored every run for transparency. NOT a
#   candidate and NOT a negative control -- no reinstatement rule.
# noise 0.00 = NEGATIVE CONTROL (2026-09-30): seeded Gaussian, null by
#   construction; validates the lab machinery (see factors/noise.py).
# yield is not in the live model -- its sleeve is still backtested
# standalone, but it gets no composite weight.
SLEEVE_WEIGHTS: dict[str, float] = {
    "quality": 0.00,
    "momentum": 0.20,
    "value": 0.20,
    "lowvol": 0.10,
    "size": 0.00,
    "growth": 0.00,
    "noise": 0.00,
}


def sleeve_zscores(frame: pd.DataFrame,
                   sleeves: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Per-sleeve mean z-score columns (``sleeve_<name>``), pairwise-complete."""
    sleeves = sleeves or SLEEVES
    out = pd.DataFrame(index=frame.index)
    for sleeve, members in sleeves.items():
        cols = [f"z_{m}" for m in members if f"z_{m}" in frame.columns]
        out[f"sleeve_{sleeve}"] = (
            frame[cols].mean(axis=1, skipna=True) if cols
            else np.nan
        )
    return out


def composite_zscore(frame: pd.DataFrame,
                     sleeves: dict[str, list[str]] | None = None,
                     weights: dict[str, float] | None = None) -> pd.Series:
    """Sleeve-weighted composite z-score, renormalized per ticker."""
    sleeves = sleeves or SLEEVES
    weights = weights or SLEEVE_WEIGHTS
    unknown = [s for s in weights if s not in sleeves]
    if unknown:
        raise KeyError(f"weights for unknown sleeves: {unknown}")
    comp = pd.Series(0.0, index=frame.index)
    wsum = pd.Series(0.0, index=frame.index)
    for sleeve, w in weights.items():
        if w == 0:
            continue
        cols = [f"z_{m}" for m in sleeves[sleeve] if f"z_{m}" in frame.columns]
        if not cols:
            continue
        sz = frame[cols].mean(axis=1, skipna=True)
        ok = sz.notna()
        comp[ok] = comp[ok] + w * sz[ok]
        wsum[ok] = wsum[ok] + w
    comp = comp / wsum.where(wsum > 0)
    return comp.rename("z_composite")
