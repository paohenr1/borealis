"""Signal half-life: how fast the cross-sectional factor ordering decays.

For base dates and trading-day lags L, the rank autocorrelation between the
factor ranks at t and at t+L (common tickers, Pearson of ranks). Half-life is
the lag where the mean autocorrelation first crosses 0.5, linearly
interpolated between bracketing lags. Lags are trading-day offsets resolved
against the panel's actual date index (weekends/holidays handled exactly).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_LAGS = [5, 21, 42, 63, 126, 189, 252]
HALF_THRESHOLD = 0.5


def rank_autocorr(a: pd.Series, b: pd.Series, min_n: int = 30) -> float:
    """Pearson correlation of ranks over tickers present at both dates."""
    common = a.dropna().index.intersection(b.dropna().index)
    if len(common) < min_n:
        return np.nan
    return float(a.loc[common].corr(b.loc[common], method="pearson"))


def decay_curve(df: pd.DataFrame, rankcol: str,
                base_dates: list, all_dates: list,
                lags: list[int] = DEFAULT_LAGS,
                min_n: int = 30) -> dict[int, float]:
    """Mean rank autocorrelation per lag, averaged over base dates."""
    pos = {d: i for i, d in enumerate(all_dates)}
    ranks = {}
    for d, g in df.groupby("date", observed=True):
        ranks[d] = g.set_index("ticker")[rankcol]
    out: dict[int, float] = {}
    for lag in lags:
        vals = []
        for bd in base_dates:
            i = pos.get(bd)
            if i is None or i + lag >= len(all_dates):
                continue
            td = all_dates[i + lag]
            if bd in ranks and td in ranks:
                vals.append(rank_autocorr(ranks[bd], ranks[td], min_n))
        vals = [v for v in vals if not np.isnan(v)]
        out[lag] = float(np.mean(vals)) if vals else np.nan
    return out


def half_life(decay: dict[int, float],
              threshold: float = HALF_THRESHOLD) -> dict:
    """First lag where autocorrelation crosses `threshold` (interpolated).

    Returns {"days": float|None, "censored": str|None}. Non-monotonic decay
    uses the first crossing, which is the conventional choice.
    """
    lags = sorted(k for k, v in decay.items() if not np.isnan(v))
    if not lags:
        return {"days": None, "censored": "no-data"}
    vals = [decay[lag] for lag in lags]
    if vals[0] < threshold:
        return {"days": float(lags[0]), "censored": "below-threshold-at-first-lag"}
    for prev_lag, lag, prev_v, v in zip(lags, lags[1:], vals, vals[1:]):
        if v <= threshold <= prev_v and prev_v != v:
            frac = (prev_v - threshold) / (prev_v - v)
            return {"days": float(prev_lag + frac * (lag - prev_lag)),
                    "censored": None}
    return {"days": float(lags[-1]),
            "censored": f"above-{threshold}-at-max-lag"}
