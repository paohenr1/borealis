"""Per-sleeve costed backtests reusing the quintile engine.

Same spec as the first composite backtest (``scripts/backtest_panel.py``):
monthly rebalance, t+1 execution, 10 bps one-way costs charged on both
legs of the dollar-neutral spread, gap-vs-permanent delist treatment
(0.0 / -0.3 Shumway 1997), per-period 1/99 cross-sectional winsorization
of holding returns.

The only difference: the signal is one sleeve's sector-neutral z-score
instead of the composite. Universe per sleeve = tickers with a non-NaN
sleeve z at the rebalance date -- each factor is tested on its own
coverable universe (e.g. momentum covers ~22.6k price-universe tickers,
quality ~5.9k fundamental tickers). Forcing the composite universe would
cripple the price-based sleeves, so this is the standard choice; it is
stated here because spread magnitudes are not directly comparable
across sleeves with different universes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from borealis.backtest import panel_backtest as pb
from borealis.backtest.engine import BacktestConfig, BacktestResult, run_backtest

COST_BPS = 10.0


def sleeve_signal_matrix(sig_frame: pd.DataFrame, sleeve: str,
                         price_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Sleeve z-score pivoted to (date x ticker), forward-filled daily.

    Mirrors ``panel_backtest.signal_matrix`` (which hardcodes z_composite):
    ffill puts z(m_k) on every trading day in (m_k, m_k+1], and the
    engine's signal_lag=1 shift reads it back at the trade date m_k + 1.
    """
    col = f"sleeve_{sleeve}"
    if col not in sig_frame.columns:
        # sleeve with no scored members: all-NaN signal (never held)
        return pd.DataFrame(np.nan, index=price_index, columns=[])
    s = sig_frame.pivot_table(index="date", columns="ticker", values=col,
                              aggfunc="last")
    return s.reindex(price_index).ffill()


def run_sleeve_backtests(prices: pd.DataFrame, sig_frame: pd.DataFrame,
                         trade_dates: pd.DatetimeIndex,
                         sleeves: list[str],
                         costs: tuple[float, ...] = (0.0, COST_BPS),
                         perm_delist_fill: float = -0.3
                         ) -> dict[str, dict[float, BacktestResult]]:
    """Run the costed quintile engine once per sleeve.

    The exit-fill matrix (delist treatment) is built once from the shared
    price matrix and reused across sleeves.
    """
    exit_fill = pb.build_exit_fill(prices, trade_dates,
                                   perm_fill=perm_delist_fill)
    out: dict[str, dict[float, BacktestResult]] = {}
    for sleeve in sleeves:
        sig_mat = sleeve_signal_matrix(sig_frame, sleeve, prices.index)
        # identical columns to prices so the engine's shape check passes;
        # tickers never scored by this sleeve are all-NaN (never held)
        sig_mat = sig_mat.reindex(columns=prices.columns)
        runs: dict[float, BacktestResult] = {}
        for cost in costs:
            cfg = BacktestConfig(
                n_quantiles=5, signal_lag=1, cost_bps=cost,
                rebalance_dates=list(trade_dates), periods_per_year=12,
                delist_fill=perm_delist_fill, exit_fill=exit_fill,
                winsorize_hold=(0.01, 0.99))
            runs[cost] = run_backtest(prices, sig_mat, cfg)
        out[sleeve] = runs
    return out


def sleeve_spread_report(runs: dict[str, dict[float, BacktestResult]],
                         cost: float = COST_BPS) -> pd.DataFrame:
    """Per-sleeve L/S spread stats plus the Q1-avoidance decomposition.

    Columns: the standard spread summary (ann return, vol, Sharpe, max
    DD, turnover, hit rate, cumulative) plus annualized net Q1/Q3/Q5
    means and the long/short contribution split:
      long_contrib  = ann(Q5) - ann(Q3)   (picking winners)
      short_contrib = ann(Q3) - ann(Q1)   (avoiding losers)
      short_share   = short_contrib / spread  (NaN when spread ~ 0)
    """
    rows = []
    for sleeve, r in runs.items():
        summ = pb.summarize_spread(r[0.0], r[cost], cost)
        q = r[cost].quantile_returns
        ann = {c: float(q[c].mean() * 12) for c in ("Q1", "Q3", "Q5")
               if c in q.columns}
        long_contrib = ann.get("Q5", np.nan) - ann.get("Q3", np.nan)
        short_contrib = ann.get("Q3", np.nan) - ann.get("Q1", np.nan)
        spread = long_contrib + short_contrib
        rows.append({
            "sleeve": sleeve,
            **summ,
            "q1_ann": ann.get("Q1", np.nan),
            "q3_ann": ann.get("Q3", np.nan),
            "q5_ann": ann.get("Q5", np.nan),
            "long_contrib": long_contrib,
            "short_contrib": short_contrib,
            "short_share": (short_contrib / spread
                            if np.isfinite(spread) and abs(spread) > 1e-12
                            else np.nan),
        })
    return pd.DataFrame(rows).set_index("sleeve").sort_index()
