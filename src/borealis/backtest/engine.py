"""Costed quintile backtest engine with strict point-in-time discipline.

A signal dated t may only drive positions from t + signal_lag onward.
Rebalance every `rebalance_every` periods; quintiles are equal-weighted;
one-way transaction costs are charged on measured turnover.

Assumption (documented): rebalance periods are treated as equal-length when
annualizing statistics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    n_quantiles: int = 5
    signal_lag: int = 1
    rebalance_every: int = 21
    cost_bps: float = 10.0
    long_only: bool = True
    periods_per_year: int = 12  # for annualization of rebalance-period stats
    # Explicit trade dates (e.g. month-end + 1 trading day). When given,
    # these positions in the price/signal index are used instead of the
    # every-`rebalance_every`-periods grid. The signal_lag shift still
    # applies: a trade at dates[i] uses the signal as of dates[i - lag].
    rebalance_dates: list | None = None
    # Holding-period return assumed when a ticker has a valid entry price
    # but no exit price (delisted mid-period). None keeps NaN (period then
    # contributes 0 via the final fillna); -1.0 is the conservative
    # total-loss assumption.
    delist_fill: float | None = -1.0
    # Optional per-exit-date fill matrix for missing exit prices
    # (index = trade dates, columns = tickers). Where it has a value, that
    # value is booked instead of `delist_fill`. Lets the driver distinguish
    # data gaps / ticker changes (book 0.0 -- the position is stuck but not
    # worthless) from permanent disappearances (book `delist_fill`).
    # Classifying on *price existence* after the exit date uses no return
    # information, so this introduces no return lookahead.
    exit_fill: pd.DataFrame | None = None
    # Optional (lo, hi) quantiles for per-period cross-sectional
    # winsorization of holding returns, e.g. (0.01, 0.99). Guards against
    # corrupt adjusted prices (a single +1e7% data error would otherwise
    # dominate an equal-weighted quantile). Applied to observed returns
    # only, before the delisting fill. Matches the lab's quintile
    # methodology. None disables.
    winsorize_hold: tuple[float, float] | None = None


@dataclass
class BacktestResult:
    quantile_returns: pd.DataFrame  # rebalance-date indexed, net of costs
    turnover: pd.DataFrame
    stats: pd.DataFrame            # ann_return, ann_vol, sharpe, max_dd per quantile


def _max_drawdown(returns: pd.Series) -> float:
    cum = (1 + returns).cumprod()
    return float((cum / cum.cummax() - 1).min())


def run_backtest(prices: pd.DataFrame, signals: pd.DataFrame,
                 cfg: BacktestConfig) -> BacktestResult:
    if not prices.index.equals(signals.index):
        raise ValueError("prices and signals must share the same DatetimeIndex")
    if not prices.columns.equals(signals.columns):
        raise ValueError("prices and signals must share the same tickers")

    sig = signals.shift(cfg.signal_lag)  # <-- the entire lookahead defense
    dates = prices.index
    if cfg.rebalance_dates is not None:
        trade_dates = pd.DatetimeIndex(cfg.rebalance_dates)
        missing = trade_dates.difference(dates)
        if len(missing):
            raise ValueError(f"rebalance_dates not in price index: "
                             f"{missing[:5].tolist()}")
        reb_idx = [dates.get_loc(d) for d in trade_dates]
    else:
        reb_idx = list(range(0, len(dates), cfg.rebalance_every))

    qs = range(1, cfg.n_quantiles + 1)
    qrets: dict[int, list[float]] = {q: [] for q in qs}
    qturn: dict[int, list[float]] = {q: [] for q in qs}
    labels_idx: list = []
    prev_w = {q: pd.Series(0.0, index=prices.columns) for q in qs}

    for k, i in enumerate(reb_idx):
        s = sig.iloc[i].dropna()
        if s.nunique() < cfg.n_quantiles:
            continue  # not enough dispersion to form quantiles
        labels = pd.qcut(s, cfg.n_quantiles, labels=False, duplicates="drop") + 1
        j = reb_idx[k + 1] if k + 1 < len(reb_idx) else len(dates) - 1
        if j <= i:
            continue
        entry_px = prices.iloc[i]
        exit_px = prices.iloc[j]
        hold = exit_px / entry_px - 1.0
        if cfg.winsorize_hold is not None:
            # cross-sectional winsorization of observed holding returns
            # (data-error defense); delisted names handled separately below
            obs = entry_px.notna() & exit_px.notna()
            if obs.any():
                lo = float(hold[obs].quantile(cfg.winsorize_hold[0]))
                hi = float(hold[obs].quantile(cfg.winsorize_hold[1]))
                if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                    hold = hold.mask(obs, hold.clip(lo, hi))
        if cfg.delist_fill is not None or cfg.exit_fill is not None:
            # valid entry price but no exit price: delisted (or gappy) mid-period
            missing_exit = entry_px.notna() & exit_px.isna()
            if missing_exit.any():
                fill = (pd.Series(cfg.delist_fill, index=prices.columns)
                        if cfg.delist_fill is not None
                        else pd.Series(np.nan, index=prices.columns))
                if (cfg.exit_fill is not None
                        and dates[j] in cfg.exit_fill.index):
                    fr = cfg.exit_fill.loc[dates[j]].reindex(prices.columns)
                    fill = fr.where(fr.notna(), fill)
                hold = hold.mask(missing_exit, fill)
        hold = hold.fillna(0.0)  # never-held tickers contribute nothing
        labels_idx.append(dates[i])
        for q in qs:
            members = labels[labels == q].index
            w = pd.Series(0.0, index=prices.columns)
            if len(members):
                w[members] = 1.0 / len(members)
            gross = float((w * hold).sum())
            tnover = float(0.5 * (w - prev_w[q]).abs().sum())
            qrets[q].append(gross - tnover * cfg.cost_bps / 1e4)
            qturn[q].append(tnover)
            prev_w[q] = w

    qret_df = pd.DataFrame(qrets, index=pd.DatetimeIndex(labels_idx)).fillna(0.0)
    qret_df.columns = [f"Q{q}" for q in qs]
    qturn_df = pd.DataFrame(qturn, index=pd.DatetimeIndex(labels_idx)).fillna(0.0)
    qturn_df.columns = [f"Q{q}" for q in qs]

    stats = {}
    for col in qret_df.columns:
        r = qret_df[col]
        ann_ret = float(r.mean() * cfg.periods_per_year)
        ann_vol = float(r.std() * np.sqrt(cfg.periods_per_year)) if len(r) > 1 else 0.0
        stats[col] = {
            "ann_return": ann_ret,
            "ann_vol": ann_vol,
            "sharpe": ann_ret / ann_vol if ann_vol else 0.0,
            "max_dd": _max_drawdown(r),
            "avg_turnover": float(qturn_df[col].mean()) if len(qturn_df) else 0.0,
        }
    return BacktestResult(qret_df, qturn_df,
                          pd.DataFrame(stats).T[["ann_return", "ann_vol", "sharpe", "max_dd", "avg_turnover"]])
