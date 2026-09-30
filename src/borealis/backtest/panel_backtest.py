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
  5. costed quintile engine -> PRIMARY: long-only Q5 vs SPY (10bps
     one-way on the long side); the long-short (Q5-Q1) spread is kept
     as a diagnostic only (shorting cut 2026-09-30: the short book was
     unshortable junk, modeled short costs fiction)

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


def large_cap_universe(panel_dir: str | Path,
                       month_ends: list[pd.Timestamp],
                       top_n: int = 1000) -> pd.DataFrame:
    """Eligible (date, ticker) pairs for a large-cap-only lab run.

    At each month-end, ranks tickers by ``enterprise_value`` (falling back
    to ``market_cap`` where EV is missing/nonpositive) and keeps the top
    ``top_n``. The panel is point-in-time, so the values are as known at
    the rebalance date -- no lookahead. Tickers with neither EV nor market
    cap (e.g. ETFs like SPY) are excluded; callers that need SPY (regimes)
    must add it back explicitly.
    """
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    cols = [c for c in ("ticker", "date", "enterprise_value", "market_cap")
            if c in dataset.schema.names]
    table = dataset.to_table(
        columns=cols,
        filter=ds.field("date").isin([pd.Timestamp(d) for d in month_ends]),
    )
    df = table.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    ev = pd.to_numeric(df["enterprise_value"], errors="coerce")
    mc = pd.to_numeric(df["market_cap"], errors="coerce")
    rank_key = ev.where(ev > 0)
    rank_key = rank_key.fillna(mc.where(mc > 0))
    df = df.assign(rank_key=rank_key).dropna(subset=["rank_key"])
    df["rank"] = df.groupby("date")["rank_key"].rank(ascending=False,
                                                     method="first")
    elig = df.loc[df["rank"] <= top_n, ["date", "ticker"]].copy()
    elig["ticker"] = elig["ticker"].astype(str)
    return elig.reset_index(drop=True)


def panel_trading_dates(panel_dir: str | Path) -> list[pd.Timestamp]:
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    all_dates = sorted(t.as_py() for t in
                       dataset.to_table(columns=["date"]).column("date").unique())
    return [pd.Timestamp(d) for d in all_dates]


def build_signal_frame(panel_dir: str | Path,
                       prices_path: str | Path,
                       month_ends: list[pd.Timestamp],
                       factors: list[str] | None = None,
                       pre_filter_top_n: int | None = None) -> pd.DataFrame:
    """One row per (month-end, ticker): z_composite + sleeve z-scores.

    If ``pre_filter_top_n`` is given, the frame is restricted to the
    top-N tickers by enterprise_value at each month-end BEFORE z-scoring,
    so sector-neutral z-scores are computed within the large-cap universe
    (as the live model does within its 518). Without it, z-scores come
    from the full panel cross-section and any universe filter must be
    applied afterwards by the caller.
    """
    panel_dir = Path(panel_dir)
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    if factors is None:
        factors = preprocess.available_factors(dataset.schema.names)
        factors = factors + [f for f in PROXY_FACTORS if f not in factors]
    frame = load_lab_frame(panel_dir, month_ends, factors, need_returns=False)
    if pre_filter_top_n is not None:
        elig = large_cap_universe(panel_dir, month_ends, pre_filter_top_n)
        frame = frame.merge(elig, on=["date", "ticker"], how="inner")
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


def spy_benchmark(panel_dir: str | Path,
                  trade_dates: pd.DatetimeIndex) -> pd.Series:
    """SPY buy-and-hold total return per holding period (t0 -> t1).

    Same trade calendar as the engine, so the series aligns 1:1 with the
    Q5 leg's monthly returns. adj_close is split/dividend adjusted, i.e.
    total return. Raises if SPY has no prices on the calendar.
    """
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    table = dataset.to_table(
        columns=["date", "adj_close"],
        filter=ds.field("ticker") == "SPY",
    )
    df = table.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    spy = df.set_index("date")["adj_close"].astype(float).sort_index()
    spy = spy.reindex(trade_dates).ffill()
    if spy.isna().any():
        missing = spy[spy.isna()].index.tolist()
        raise ValueError(f"SPY missing prices on trade dates: {missing[:5]}")
    rets = (spy.shift(-1) / spy - 1.0).iloc[:-1]
    rets.index = trade_dates[:-1]
    return rets.rename("spy")


def summarize_longonly(q5: pd.Series, turnover: pd.Series,
                       spy: pd.Series) -> dict:
    """Long-only Q5 vs SPY: absolute stats plus active (benchmark-relative).

    q5: Q5 leg net monthly returns (costs already charged by the engine).
    turnover: Q5 one-way turnover per period. spy: SPY monthly returns on
    the same calendar. All three are aligned on their common index.
    """
    idx = q5.index.intersection(turnover.index).intersection(spy.index)
    q5, turnover, spy = q5.loc[idx], turnover.loc[idx], spy.loc[idx]
    n = len(q5)
    ann_ret = float(q5.mean() * 12) if n else 0.0
    ann_vol = float(q5.std() * np.sqrt(12)) if n > 1 else 0.0
    cum = (1 + q5).cumprod()
    roll_max = cum.cummax()
    dd = cum / roll_max - 1.0
    max_dd = float(dd.min()) if n else 0.0
    trough = dd.idxmin() if n else None
    peak = cum.loc[:trough].idxmax() if n else None
    rec = dd.loc[trough:][dd.loc[trough:] >= 0]
    recovered = rec.index[0] if len(rec) else None
    active = q5 - spy
    a_ret = float(active.mean() * 12) if n else 0.0
    a_vol = float(active.std() * np.sqrt(12)) if n > 1 else 0.0
    return {
        "periods": n,
        "ann_return": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": ann_ret / ann_vol if ann_vol else 0.0,
        "max_drawdown": max_dd,
        "max_dd_peak": peak.isoformat() if peak is not None else None,
        "max_dd_trough": trough.isoformat() if trough is not None else None,
        "max_dd_recovered": (recovered.isoformat()
                             if recovered is not None else None),
        "avg_turnover_oneway": float(turnover.mean()) if n else 0.0,
        "hit_rate": float((q5 > 0).mean()) if n else 0.0,
        "spy_ann_return": float(spy.mean() * 12) if n else 0.0,
        "ann_active_return": a_ret,
        "ann_tracking_error": a_vol,
        "information_ratio": a_ret / a_vol if a_vol else 0.0,
        "hit_rate_vs_spy": float((active > 0).mean()) if n else 0.0,
        "cumulative": float(cum.iloc[-1] - 1) if n else 0.0,
        "cumulative_active": float(((1 + active).cumprod().iloc[-1] - 1)
                                   if n else 0.0),
    }


def equal_weight_benchmark(prices: pd.DataFrame,
                           trade_dates: pd.DatetimeIndex,
                           universe: pd.DataFrame,
                           exit_fill: pd.DataFrame | None = None
                           ) -> pd.Series:
    """Per-period equal-weighted total return of signal-eligible tickers.

    Delisting economics mirror the engine: names with no exit price book
    0.0 when they trade again later (data gap / ticker change) and -0.3
    when permanently delisted (via ``exit_fill``; build with
    build_exit_fill to match the main spec). Booking -1.0 on every gap
    would phantom-bankrupt the benchmark on gappy microcaps.
    """
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
        e0, e1 = prices.loc[t0, members], prices.loc[t1, members]
        h = e1 / e0 - 1.0
        # same corrupt-price defense as the engine: 1/99 winsorization of
        # observed holding returns, before delisting fills
        obs = e0.notna() & e1.notna()
        if obs.any():
            lo, hi = float(h[obs].quantile(0.01)), float(h[obs].quantile(0.99))
            if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                h = h.mask(obs, h.clip(lo, hi))
        missing_exit = e0.notna() & e1.isna()
        if missing_exit.any():
            if exit_fill is not None and t1 in exit_fill.index:
                fr = exit_fill.loc[t1].reindex(members)
                h = h.mask(missing_exit & fr.notna(), fr)
                h = h.mask(missing_exit & fr.isna(), 0.0)
            else:
                h = h.mask(missing_exit, -1.0)
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


def cap_weight_frame(panel_dir: str | Path,
                      month_ends: list[pd.Timestamp],
                      tickers: list[str]) -> pd.DataFrame:
    """Point-in-time market_cap per (month-end, ticker), pivoted date x ticker.

    The panel is point-in-time, so values are as known at the rebalance
    date -- no lookahead. Used to cap-weight the Q5 long-only leg.
    """
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    cols = ["ticker", "date", "market_cap"]
    filt = (ds.field("date").isin([pd.Timestamp(d) for d in month_ends])
            & ds.field("ticker").isin(tickers))
    table = dataset.to_table(
        columns=[c for c in cols if c in dataset.schema.names],
        filter=filt,
    )
    df = table.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    df["market_cap"] = pd.to_numeric(df["market_cap"], errors="coerce")
    cap = df.pivot_table(index="date", columns="ticker", values="market_cap",
                         aggfunc="last").sort_index()
    return cap.reindex([pd.Timestamp(d) for d in month_ends])


def cap_weighted_q5(prices: pd.DataFrame, sig_mat: pd.DataFrame,
                    trade_dates: pd.DatetimeIndex,
                    cap_mat: pd.DataFrame,
                    cost_bps: float = 10.0,
                    exit_fill: pd.DataFrame | None = None,
                    winsorize_hold: tuple[float, float] | None = (0.01, 0.99),
                    delist_fill: float | None = -0.3
                    ) -> tuple[pd.Series, pd.Series]:
    """Cap-weighted Q5 long-only leg: net returns + one-way turnover.

    Mirrors ``run_backtest`` exactly (same Q5 membership via qcut, same
    t+1 signal timing, same holding-return winsorization and delisting
    economics) except holdings are weighted by point-in-time market cap at
    the signal month-end instead of equal-weighted. Members with missing
    or nonpositive caps are excluded and the rest renormalized; if no
    member has a valid cap, the period falls back to equal weight
    (documented, rare on large caps).
    Turnover uses the engine's target-to-target convention
    (0.5 * |w_new - w_prev|) for comparability with the EW leg.
    Returns (net_returns, turnover), indexed by trade date.
    """
    if not prices.index.equals(sig_mat.index):
        raise ValueError("prices and sig_mat must share the same DatetimeIndex")
    if not prices.columns.equals(sig_mat.columns):
        raise ValueError("prices and sig_mat must share the same tickers")
    dates = prices.index
    sig = sig_mat.shift(1)  # same lookahead defense as the engine
    reb_idx = [dates.get_loc(d) for d in trade_dates]

    rets: list[float] = []
    turns: list[float] = []
    idx: list = []
    prev_w = pd.Series(0.0, index=prices.columns)
    for k, i in enumerate(reb_idx):
        s = sig.iloc[i].dropna()
        if s.nunique() < 5:
            continue  # not enough dispersion to form quintiles
        labels = pd.qcut(s, 5, labels=False, duplicates="drop") + 1
        members = labels[labels == 5].index
        j = reb_idx[k + 1] if k + 1 < len(reb_idx) else len(dates) - 1
        if j <= i or not len(members):
            continue
        # signal month-end = the trading day whose signal we just read
        me = dates[i - 1]
        w = pd.Series(0.0, index=prices.columns)
        if me in cap_mat.index:
            caps = pd.to_numeric(cap_mat.loc[me].reindex(members),
                                 errors="coerce")
            valid = caps[caps > 0].dropna()
            if len(valid):
                w[valid.index] = valid / valid.sum()
        if w.sum() == 0.0:
            w[members] = 1.0 / len(members)  # documented fallback
        entry_px = prices.iloc[i]
        exit_px = prices.iloc[j]
        hold = exit_px / entry_px - 1.0
        if winsorize_hold is not None:
            obs = entry_px.notna() & exit_px.notna()
            if obs.any():
                lo = float(hold[obs].quantile(winsorize_hold[0]))
                hi = float(hold[obs].quantile(winsorize_hold[1]))
                if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                    hold = hold.mask(obs, hold.clip(lo, hi))
        if delist_fill is not None or exit_fill is not None:
            missing_exit = entry_px.notna() & exit_px.isna()
            if missing_exit.any():
                fill = (pd.Series(delist_fill, index=prices.columns)
                        if delist_fill is not None
                        else pd.Series(np.nan, index=prices.columns))
                if exit_fill is not None and dates[j] in exit_fill.index:
                    fr = exit_fill.loc[dates[j]].reindex(prices.columns)
                    fill = fr.where(fr.notna(), fill)
                hold = hold.mask(missing_exit, fill)
        hold = hold.fillna(0.0)
        gross = float((w * hold).sum())
        tnover = float(0.5 * (w - prev_w).abs().sum())
        rets.append(gross - tnover * cost_bps / 1e4)
        turns.append(tnover)
        idx.append(dates[i])
        prev_w = w
    q = pd.Series(rets, index=pd.DatetimeIndex(idx), name="Q5_capweight")
    t = pd.Series(turns, index=pd.DatetimeIndex(idx), name="Q5_capweight")
    return q, t


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
