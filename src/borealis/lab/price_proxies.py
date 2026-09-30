"""Price-derived factor proxies: 12-1 momentum, trailing volatility, beta.

Built from daily split/dividend-adjusted closes (``prices_clean.parquet``),
so they cover the full price universe, unlike fundamental factors (which
cover ~5.9k of 22.6k tickers).

Construction (judgment calls documented):
- ``mom_12m1m(t) = adj_close(t-21) / adj_close(t-252) - 1``: 12-month
  trailing total return skipping the most recent month (standard 12-1;
  avoids short-term reversal contamination). NaN with < 252 trading days
  of history, so the momentum sample starts ~2021-02 (panel starts
  2020-01-24).
- ``vol_126d(t)``: sample std (ddof=1) of daily simple total returns over
  the 126 trading days ending at t, annualized x sqrt(252). NaN with
  < 126 observations.
- ``beta_252d(t)`` (added 2026-09-30): 252-trading-day beta vs SPY --
  cov(stock daily returns, SPY daily returns) / var(SPY daily returns),
  pairwise-complete, min 252 valid pairs. Matches the live low-vol
  definition (trailing beta vs SPY). NaN with < 252 trading days of
  overlapping history.

No lookahead: every input is a price on or before t (momentum's latest
input is t-21). Read-only on the price file.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MOM_SKIP = 21       # trading days skipped (most recent month)
MOM_LOOKBACK = 252  # trading days of formation window
VOL_WINDOW = 126    # trading days of volatility estimation
BETA_WINDOW = 252   # trading days of beta estimation vs SPY
BETA_BENCHMARK = "SPY"

# calendar-day pad guaranteeing >= MOM_LOOKBACK trading days of history
_LOOKBACK_PAD_DAYS = 450


def compute_price_proxies(prices_path: str | Path,
                          dates: list) -> pd.DataFrame:
    """Return ``(date, ticker, mom_12m1m, vol_126d, beta_252d)`` for the given dates.

    Offsets are per-ticker trading days (row positions within each
    ticker's sorted history), so delisted names with gappy histories are
    handled naturally.
    """
    dates = pd.to_datetime(pd.Series(sorted(set(pd.to_datetime(dates)))))
    df = pd.read_parquet(prices_path, columns=["ticker", "date", "adj_close"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["adj_close"])
    df = df[df["adj_close"] > 0]
    cutoff = dates.min() - pd.Timedelta(days=_LOOKBACK_PAD_DAYS)
    df = df[df["date"] >= cutoff]
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    by_ticker = df.groupby("ticker", sort=False)["adj_close"]
    df["mom_12m1m"] = (by_ticker.shift(MOM_SKIP) /
                       by_ticker.shift(MOM_LOOKBACK) - 1)
    df["vol_126d"] = (
        by_ticker.transform(
            lambda s: s.pct_change()
            .rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std(ddof=1))
        * np.sqrt(252)
    )
    # 252d beta vs SPY on daily simple returns (the live low-vol definition).
    df["ret"] = by_ticker.transform(lambda s: s.pct_change())
    spy_ret = (df.loc[df["ticker"] == BETA_BENCHMARK, ["date", "ret"]]
                 .rename(columns={"ret": "spy_ret"}))
    m = df.merge(spy_ret, on="date", how="left")

    def _beta(g: pd.DataFrame) -> pd.Series:
        r, s = g["ret"], g["spy_ret"]
        cov = r.rolling(BETA_WINDOW, min_periods=BETA_WINDOW).cov(s)
        var = s.rolling(BETA_WINDOW, min_periods=BETA_WINDOW).var(ddof=1)
        return (cov / var).rename("beta_252d")

    beta = m.groupby("ticker", sort=False).apply(_beta)
    beta.index = beta.index.droplevel(0)  # back to the original row index
    df["beta_252d"] = beta.sort_index()
    out = df.loc[df["date"].isin(dates),
                 ["ticker", "date", "mom_12m1m", "vol_126d", "beta_252d"]]
    return out.reset_index(drop=True)
