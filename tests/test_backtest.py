"""Tests for the backtest engine: lookahead defense and cost handling."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.backtest.engine import BacktestConfig, run_backtest


def _toy_panels():
    dates = pd.date_range("2020-01-01", periods=6, freq="D")
    cols = ["A", "B", "C", "D", "E"]
    # A jumps +50% between day 0 and day 1, flat afterwards
    prices = pd.DataFrame(100.0, index=dates, columns=cols)
    prices.loc[dates[1]:, "A"] = 150.0
    # Signal at day 0 ranks A first (5 distinct values -> quintiles form)
    signals = pd.DataFrame(0.0, index=dates, columns=cols)
    signals.loc[dates[0]] = [5.0, 4.0, 3.0, 2.0, 1.0]
    return prices, signals


class TestLookahead(unittest.TestCase):
    def test_lag_zero_captures_jump(self):
        prices, signals = _toy_panels()
        cfg = BacktestConfig(n_quantiles=5, signal_lag=0, rebalance_every=1,
                             cost_bps=0.0, periods_per_year=252)
        res = run_backtest(prices, signals, cfg)
        self.assertGreater(res.quantile_returns["Q5"].iloc[0], 0.4)

    def test_lag_one_misses_jump(self):
        prices, signals = _toy_panels()
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, rebalance_every=1,
                             cost_bps=0.0, periods_per_year=252)
        res = run_backtest(prices, signals, cfg)
        # signal shifted past the jump -> top quantile should not capture it
        self.assertLess(res.quantile_returns["Q5"].iloc[0], 0.4)

    def test_mismatched_panels_rejected(self):
        prices, signals = _toy_panels()
        cfg = BacktestConfig()
        with self.assertRaises(ValueError):
            run_backtest(prices, signals.drop(columns=["E"]), cfg)


class TestCosts(unittest.TestCase):
    def test_costs_reduce_returns(self):
        prices, signals = _toy_panels()
        free = run_backtest(prices, signals,
                            BacktestConfig(signal_lag=0, rebalance_every=1, cost_bps=0.0))
        costly = run_backtest(prices, signals,
                              BacktestConfig(signal_lag=0, rebalance_every=1, cost_bps=10000.0))
        self.assertLess(costly.quantile_returns["Q5"].sum(),
                        free.quantile_returns["Q5"].sum())

    def test_stats_present(self):
        prices, signals = _toy_panels()
        res = run_backtest(prices, signals, BacktestConfig(cost_bps=0.0))
        self.assertIn("sharpe", res.stats.columns)
        self.assertIn("max_dd", res.stats.columns)


if __name__ == "__main__":
    unittest.main()
