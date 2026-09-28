"""IC decay across forward-return horizons.

For each signal (month-end) date t and horizon h in trading days, the
forward total return fwd_h(t) = adj_close(t+h) / adj_close(t) - 1 is read
off the daily price matrix. Pairing z(t) with returns strictly after t
keeps the point-in-time discipline; computing the forward return from
later prices is exactly what a forward return is (the panel's own
ret_fwd_21d/ret_fwd_63d are built the same way).

Per sleeve and horizon: Spearman rank IC series + summary. IC half-life
is the horizon where the mean IC first falls to half its 21-day value,
linearly interpolated on the horizon grid (censored when it never
crosses within the grid).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from borealis.lab import ic as lab_ic

HORIZONS = (21, 63, 126, 252)


def forward_returns(prices: pd.DataFrame,
                    signal_dates: list,
                    horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    """Long frame (date, ticker, h, fwd_ret) of forward total returns.

    ``prices``: daily adj_close indexed by date, columns = tickers.
    Horizons are trading-day offsets resolved on the price index, so
    weekends/holidays are handled exactly. Dates too close to the sample
    end for a horizon are skipped for that horizon (n reported downstream).
    """
    pos = {d: i for i, d in enumerate(prices.index)}
    n_days = len(prices)
    frames = []
    for h in horizons:
        rows = []
        for d in signal_dates:
            d = pd.Timestamp(d)
            i = pos.get(d)
            if i is None or i + h >= n_days:
                continue
            fwd = prices.iloc[i + h] / prices.iloc[i] - 1.0
            fwd = fwd.dropna()
            if len(fwd):
                rows.append(pd.DataFrame(
                    {"date": d, "ticker": fwd.index, "h": h,
                     "fwd_ret": fwd.values}))
        if rows:
            frames.append(pd.concat(rows, ignore_index=True))
    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "h", "fwd_ret"])
    return pd.concat(frames, ignore_index=True)


def ic_at_horizons(sig_long: pd.DataFrame, fwd: pd.DataFrame,
                   sleeves: list[str],
                   min_n: int = 30) -> dict[str, dict[int, dict]]:
    """Per sleeve, per horizon: IC series summary (mean/tstat/hit/n).

    ``sig_long``: columns date, ticker, sleeve_<name>. Merged with ``fwd``
    on (date, ticker, h); IC computed cross-sectionally per (date, h).
    """
    out: dict[str, dict[int, dict]] = {}
    for sleeve in sleeves:
        zc = f"sleeve_{sleeve}"
        if zc not in sig_long.columns:
            continue
        m = sig_long[["date", "ticker", zc]].merge(
            fwd, on=["date", "ticker"], how="inner")
        m = m.dropna(subset=[zc, "fwd_ret"])
        per_h: dict[int, dict] = {}
        for h, g in m.groupby("h", observed=True):
            ics = lab_ic.ic_series(g, zc, "fwd_ret", min_n=min_n)
            per_h[int(h)] = lab_ic.ic_summary(ics)
        out[sleeve] = per_h
    return out


def ic_half_life(ic_means: dict[int, float],
                 horizons: tuple[int, ...] = HORIZONS) -> dict:
    """Horizon where mean IC first falls to half its 21-day value.

    Linear interpolation between bracketing horizons. Returns
    {"days": float|None, "censored": str|None}.
    """
    hs = [h for h in horizons if h in ic_means
          and np.isfinite(ic_means[h])]
    if not hs:
        return {"days": None, "censored": "no-data"}
    base = ic_means[hs[0]]
    if not np.isfinite(base) or base <= 0:
        return {"days": None, "censored": "nonpositive-base-ic"}
    target = base / 2.0
    vals = [ic_means[h] for h in hs]
    if vals[0] <= target:
        return {"days": float(hs[0]),
                "censored": "below-half-at-first-horizon"}
    for h0, h1, v0, v1 in zip(hs, hs[1:], vals, vals[1:]):
        if v1 <= target <= v0 and v0 != v1:
            frac = (v0 - target) / (v0 - v1)
            return {"days": float(h0 + frac * (h1 - h0)),
                    "censored": None}
    return {"days": float(hs[-1]),
            "censored": "above-half-at-max-horizon"}
