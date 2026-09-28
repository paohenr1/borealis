"""Market-regime conditioning for factor efficacy.

Regimes are defined from SPY alone (trailing, so known at the signal
date -- no lookahead):
  - mkt_up: trailing 21-trading-day SPY total return > 0 at the signal date.
  - high_vol: trailing 63-trading-day realized vol (std of daily simple
    returns x sqrt(252)) above its median across signal dates. There is
    no VIX series in the bulk data, so realized vol is the documented
    proxy; it answers "does the factor work when markets are turbulent"
    rather than "when implied vol is high".

Per-sleeve IC series are then split by regime: mean IC, t-stat and N in
up/down and high/low-vol months, plus the difference. Regime analysis is
descriptive (few dozen months per bucket) -- it flags where a sleeve's
edge lives, it does not prove it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RET_WIN = 21
VOL_WIN = 63


def spy_regimes(prices: pd.DataFrame, signal_dates: list,
                spy_ticker: str = "SPY",
                ret_win: int = RET_WIN,
                vol_win: int = VOL_WIN) -> pd.DataFrame:
    """Trailing market return sign and realized-vol regime per signal date.

    ``prices``: daily adj_close (date x ticker). Returns DataFrame indexed
    by signal date with mkt_ret_21d, mkt_up, spy_vol_63d, high_vol.
    """
    if spy_ticker not in prices.columns:
        raise KeyError(f"{spy_ticker} not in price columns")
    px = prices[spy_ticker].dropna()
    daily = px.pct_change()
    pos = {d: i for i, d in enumerate(px.index)}
    rows = []
    for d in signal_dates:
        d = pd.Timestamp(d)
        i = pos.get(d)
        if i is None or i < vol_win:
            continue
        mkt_ret = float(px.iloc[i] / px.iloc[i - ret_win] - 1.0)
        vol = float(daily.iloc[i - vol_win + 1:i + 1].std(ddof=1)
                    * np.sqrt(252))
        rows.append({"date": d, "mkt_ret_21d": mkt_ret,
                     "spy_vol_63d": vol})
    out = pd.DataFrame(rows).set_index("date").sort_index()
    out["mkt_up"] = out["mkt_ret_21d"] > 0
    out["high_vol"] = out["spy_vol_63d"] > out["spy_vol_63d"].median()
    return out


def _summ(s: pd.Series) -> dict:
    s = s.dropna()
    n = len(s)
    if n < 2:
        return {"n": n, "mean": np.nan, "tstat": np.nan}
    mean = float(s.mean())
    std = float(s.std(ddof=1))
    return {"n": n, "mean": mean,
            "tstat": float(mean / (std / np.sqrt(n))) if std > 0 else np.nan}


def ic_by_regime(ics: pd.Series, regimes: pd.DataFrame) -> dict:
    """Split an IC series (indexed by date) by market regime.

    Returns {regime_name: {up/down or high/low: summary}, 'diff_up_down',
    'diff_high_low'} where diffs are (mean_a - mean_b) with a two-sample
    t-stat (Welch).
    """
    idx = ics.index.intersection(regimes.index)
    ics, reg = ics.loc[idx], regimes.loc[idx]
    out: dict = {}
    for flag, labels in (("mkt_up", ("up", "down")),
                         ("high_vol", ("high_vol", "low_vol"))):
        grp = {}
        for val, lab in zip((True, False), labels):
            grp[lab] = _summ(ics[reg[flag] == val])
        a = ics[reg[flag]].dropna()
        b = ics[~reg[flag]].dropna()
        if len(a) > 1 and len(b) > 1:
            se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
            diff_t = float((a.mean() - b.mean()) / se) if se > 0 else np.nan
        else:
            diff_t = np.nan
        grp["diff_tstat"] = diff_t
        out[flag] = grp
    return out
