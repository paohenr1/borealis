"""First real backtest driver: composite signal on the Intrinio PIT panel.

Pipeline (all read-only on the panel):
  1. month-end rebalance dates from the panel's trading calendar
  2. signal frame: sector-neutral z-scores per factor (lab.preprocess),
     sleeve-weighted composite (lab.composite), price proxies
     (mom_12m1m, vol_126d from prices_clean.parquet)
  3. price matrix: adj_close (total-return) pivoted to dates x tickers
  4. trade dates = month-end + 1 trading day (t+1 execution); the engine's
     signal_lag=1 shift then pairs each trade with the signal as of the
     month-end close -- no lookahead by construction
  5. costed quintile engine -> long-short (Q5-Q1) and long-only (Q5)
     vs equal-weight universe benchmark

Universe: tickers with a non-NaN composite z at the rebalance date
(same universe as the factor-efficacy lab, so IC/quintile numbers are
comparable). No price filter in the main spec; a >=$5 sensitivity is
reported separately.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from borealis.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from borealis.lab import composite as lab_composite
from borealis.lab import preprocess, price_proxies
from borealis.lab.run import PROXY_FACTORS, load_lab_frame, month_end_dates

MIN_PX_SENSITIVITY = 5.0


def panel_trading_dates(panel_dir: str | Path) -> list[pd.Timestamp]:
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    all_dates = sorted(t.as_py() for t in
                       dataset.to_table(columns=["date"]).column("date").unique())
    return [pd.Timestamp(d) for d in all_dates]


def build_signal_frame(panel_dir: str | Path,
                       prices_path: str | Path,
                       month_ends: list[pd.Timestamp],
                       factors: list[str] | None = None) -> pd.DataFrame:
    """One row per (month-end, ticker): z_composite + sleeve z-scores."""
    panel_dir = Path(panel_dir)
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    if factors is None:
        factors = preprocess.available_factors(dataset.schema.names)
        factors = factors + [f for f in PROXY_FACTORS if f not in factors]
    frame = load_lab_frame(panel_dir, month_ends, factors, need_returns=False)
    proxies = price_proxies.compute_price_proxies(prices_path, month_ends)
    frame = frame.merge(proxies, on=["ticker", "date"], how="left")
    frame = preprocess.add_lab_zscores(frame, factors)
    frame["z_composite"] = lab_composite.composite_zscore(frame)
    sleeve_z = lab_composite.sleeve_zscores(frame)
    return pd.concat([frame[["date", "ticker", "z_composite"]], sleeve_z],
                     axis=1)


def build_price_matrix(panel_dir: str | Path,
                       tickers: list[str]) -> pd.DataFrame:
    """Daily adj_close pivoted to (date x ticker). Read-only on the panel."""
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    table = dataset.to_table(
        columns=["ticker", "date", "adj_close"],
        filter=ds.field("ticker").isin(tickers),
    )
    df = table.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    px = df.pivot_table(index="date", columns="ticker", values="adj_close",
                        aggfunc="last")
    return px.sort_index()


def trade_calendar(all_dates: list[pd.Timestamp],
                   month_ends: list[pd.Timestamp]) -> pd.DatetimeIndex:
    """Trade dates: first trading day strictly after each month-end that
    still has a following trade date (so every holding period is complete)."""
    pos = {d: n for n, d in enumerate(all_dates)}
    trades = []
    for m in month_ends:
        n = pos.get(m)
        if n is None or n + 2 >= len(all_dates):
            continue
        trades.append(all_dates[n + 1])
    return pd.DatetimeIndex(trades)


def signal_matrix(signals: pd.DataFrame,
                  price_index: pd.DatetimeIndex) -> pd.DataFrame:
    """z_composite on month-end rows, forward-filled across trading days.

    Combined with trade dates = month-end + 1 and the engine's
    signal_lag=1 shift, each trade uses the signal as of the month-end
    close: ffill puts z(m_k) on every day in (m_k, m_k+1], and shift(1)
    reads it back at the trade date m_k + 1.
    """
    s = signals.pivot_table(index="date", columns="ticker",
                            values="z_composite", aggfunc="last")
    s = s.reindex(price_index).ffill()
    return s


def equal_weight_benchmark(prices: pd.DataFrame,
                           trade_dates: pd.DatetimeIndex,
                           universe: pd.DataFrame) -> pd.Series:
    """Per-period equal-weighted total return of signal-eligible tickers."""
    rets = []
    um = universe.pivot_table(index="date", columns="ticker",
                              values="z_composite", aggfunc="last").notna()
    for k in range(len(trade_dates) - 1):
        t0, t1 = trade_dates[k], trade_dates[k + 1]
        m = um.index[um.index <= t0].max()  # latest signal date <= trade
        members = um.columns[um.loc[m]].tolist()
        members = [c for c in members if c in prices.columns]
        if not members:
            rets.append(np.nan)
            continue
        h = prices.loc[t1, members] / prices.loc[t0, members] - 1.0
        h = h.mask(prices.loc[t0, members].notna()
                   & prices.loc[t1, members].isna(), -1.0)  # delisted
        # same corrupt-price defense as the engine: 1/99 winsorization
        obs = h.notna() & (h != -1.0)
        if obs.any():
            lo, hi = float(h[obs].quantile(0.01)), float(h[obs].quantile(0.99))
            if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                h = h.mask(obs, h.clip(lo, hi))
        rets.append(float(h.fillna(0.0).mean()))
    return pd.Series(rets, index=trade_dates[:-1], name="benchmark_ew")


def build_exit_fill(prices: pd.DataFrame,
                    trade_dates: pd.DatetimeIndex,
                    perm_fill: float = -0.3) -> pd.DataFrame:
    """Per-exit-date return to book when a held ticker has no exit price.

    Index = trade dates (each row is the EXIT date of the period ending
    there), columns = tickers. 0.0 where the ticker trades again later
    (data gap / ticker change -- position stuck, not worthless);
    `perm_fill` where it never trades again (permanent delisting;
    default -0.3 per Shumway 1997). Classification uses price *existence*
    only, so no return lookahead is introduced.
    """
    has_px = prices.notna()
    # strictly-after existence: reverse cummax then shift
    future_px = (has_px.iloc[::-1].cummax().iloc[::-1]
                 .shift(-1, fill_value=False))
    rows = {}
    for k in range(1, len(trade_dates)):
        t0, t1 = trade_dates[k - 1], trade_dates[k]
        e0 = has_px.loc[t0]
        missing = e0 & ~has_px.loc[t1]
        if not missing.any():
            continue
        gap = missing & future_px.loc[t1]
        perm = missing & ~future_px.loc[t1]
        row = pd.Series(np.nan, index=prices.columns)
        row = row.mask(gap, 0.0).mask(perm, perm_fill)
        rows[t1] = row
    out = pd.DataFrame(rows).T
    out.index = pd.DatetimeIndex(out.index)
    return out.reindex(trade_dates[1:])


def summarize_spread(res_gross: BacktestResult,
                     res_net: BacktestResult | None = None,
                     cost_bps: float = 0.0) -> dict:
    """Long-short Q5-Q1 stats with correct dollar-neutral cost accounting.

    A dollar-neutral L/S pays one-way costs on BOTH legs, so the net
    spread = gross spread - (turnover_Q5 + turnover_Q1) * cost. (Naively
    differencing each leg's net return would credit back the short leg's
    costs.) Pass the 0bps run as `res_gross` and the costed run as
    `res_net`; omit `res_net` for a gross-only summary.
    """
    q = res_gross.quantile_returns
    spread_gross = q["Q5"] - q["Q1"]
    if res_net is not None:
        t = res_net.turnover
        tnover = (t["Q5"] + t["Q1"]).reindex(spread_gross.index).fillna(0.0)
        spread = spread_gross - tnover * cost_bps / 1e4
    else:
        t = res_gross.turnover
        tnover = (t["Q5"] + t["Q1"]).reindex(spread_gross.index).fillna(0.0)
        spread = spread_gross
    n = len(spread)
    ann_ret = float(spread.mean() * 12)
    ann_vol = float(spread.std() * np.sqrt(12)) if n > 1 else 0.0
    cum = (1 + spread).cumprod()
    max_dd = float((cum / cum.cummax() - 1).min())
    return {
        "periods": n,
        "ann_return": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": ann_ret / ann_vol if ann_vol else 0.0,
        "max_drawdown": max_dd,
        "avg_turnover_ls": float(tnover.mean()) if n else 0.0,
        "hit_rate": float((spread > 0).mean()) if n else 0.0,
        "cumulative": float(cum.iloc[-1] - 1) if n else 0.0,
    }


def composite_ic(signals: pd.DataFrame, panel_dir: str | Path) -> dict:
    """Rank IC of z_composite(t) vs 21d forward total return after t."""
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    dates = sorted(signals["date"].unique())
    fwd = dataset.to_table(
        columns=["ticker", "date", "ret_fwd_21d"],
        filter=ds.field("date").isin([pd.Timestamp(d) for d in dates]),
    ).to_pandas()
    m = signals.merge(fwd, on=["ticker", "date"], how="inner")
    m = m.dropna(subset=["z_composite", "ret_fwd_21d"])
    ics = m.groupby("date")[["z_composite", "ret_fwd_21d"]].apply(
        lambda g: g["z_composite"].corr(g["ret_fwd_21d"], method="spearman")
    ).dropna()
    n = len(ics)
    return {
        "mean": float(ics.mean()),
        "tstat": float(ics.mean() / (ics.std() / np.sqrt(n))) if n > 1 else 0.0,
        "hit_rate": float((ics > 0).mean()),
        "n": n,
    }


def run_configs(prices: pd.DataFrame, sig_mat: pd.DataFrame,
                trade_dates: pd.DatetimeIndex,
                cost_bps_list: tuple[float, ...] = (0.0, 10.0),
                perm_delist_fill: float = -0.3) -> dict:
    """Run the engine per cost level; return {cost_bps: BacktestResult}.

    Missing exit prices: 0.0 for data gaps / ticker changes (price
    reappears later), `perm_delist_fill` for permanent delistings
    (default -0.3, Shumway 1997 compromise; use -1.0 for the
    conservative bound as a separate sensitivity).
    """
    exit_fill = build_exit_fill(prices, trade_dates, perm_fill=perm_delist_fill)
    out = {}
    for cost in cost_bps_list:
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=cost,
                             rebalance_dates=list(trade_dates),
                             periods_per_year=12,
                             delist_fill=perm_delist_fill,
                             exit_fill=exit_fill,
                             # lab-consistent: per-period 1/99 winsorization
                             # of holding returns (corrupt-price defense)
                             winsorize_hold=(0.01, 0.99))
        out[cost] = run_backtest(prices, sig_mat, cfg)
    return out
