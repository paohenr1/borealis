"""Tests for the panel-backtest engine extensions: explicit rebalance dates
and the delisting fill. The lookahead/cost core is covered by test_backtest.py.
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.backtest.engine import BacktestConfig, run_backtest
from borealis.backtest import panel_backtest as pb


def _panels(n_days=8):
    dates = pd.date_range("2020-01-01", periods=n_days, freq="D")
    cols = ["A", "B", "C", "D", "E"]
    prices = pd.DataFrame(100.0, index=dates, columns=cols)
    prices.loc[dates[2]:, "A"] = 110.0   # A +10% from day 2
    prices.loc[dates[4]:, "B"] = 120.0   # B +20% from day 4
    signals = pd.DataFrame(np.nan, index=dates, columns=cols)
    signals.loc[dates[1]] = [5.0, 4.0, 3.0, 2.0, 1.0]  # signal dated day 1
    signals.loc[dates[5]] = [1.0, 2.0, 3.0, 4.0, 5.0]  # flipped at day 5
    return prices, signals


class TestExplicitRebalanceDates(unittest.TestCase):
    def test_trade_dates_used(self):
        prices, signals = _panels()
        sig = signals.ffill()
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[prices.index[2], prices.index[6]],
                             periods_per_year=12)
        res = run_backtest(prices, sig, cfg)
        # trades at day 2 and day 6; holding periods day2->day6, day6->day7
        self.assertEqual(list(res.quantile_returns.index),
                         [prices.index[2], prices.index[6]])
        # at day 2, lagged signal = day-1 ranking -> A top quintile;
        # A rises 0% over day2->day6 (already at 110)
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], 0.0)

    def test_unknown_date_rejected(self):
        prices, signals = _panels()
        cfg = BacktestConfig(
            rebalance_dates=[pd.Timestamp("1999-01-01")])
        with self.assertRaises(ValueError):
            run_backtest(prices, signals.ffill(), cfg)


class TestDelistFill(unittest.TestCase):
    def test_delisted_member_filled(self):
        prices, signals = _panels()
        # C vanishes after day 3 (delisted); rank C top at day-1 signal
        prices.loc[prices.index[4]:, "C"] = np.nan
        sig = signals.ffill()
        sig.loc[prices.index[1]] = [1.0, 2.0, 5.0, 3.0, 4.0]  # C top
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[prices.index[2]],
                             delist_fill=-1.0)
        res = run_backtest(prices, sig, cfg)
        # Q5 holds only C: entered 100, delisted -> -100%
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], -1.0)

    def test_no_delist_fill_keeps_old_behavior(self):
        prices, signals = _panels()
        prices.loc[prices.index[4]:, "C"] = np.nan
        sig = signals.ffill()
        sig.loc[prices.index[1]] = [1.0, 2.0, 3.0, 4.0, 5.0]
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[prices.index[2]],
                             delist_fill=None)
        res = run_backtest(prices, sig, cfg)
        # NaN hold -> 0 contribution (never-held tickers contribute nothing)
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], 0.0)


class TestWinsorizeHold(unittest.TestCase):
    def test_extreme_return_clipped(self):
        dates = pd.date_range("2020-01-01", periods=4, freq="D")
        cols = [f"S{i}" for i in range(10)]
        prices = pd.DataFrame(100.0, index=dates, columns=cols)
        prices.loc[dates[2]:, "S0"] = 100.0 * 101  # +10000% data error
        signals = pd.DataFrame(np.nan, index=dates, columns=cols)
        signals.loc[dates[0]] = np.arange(10.0)  # S0 bottom quintile
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[dates[1]],
                             winsorize_hold=(0.01, 0.99))
        res = run_backtest(prices, signals.ffill(), cfg)
        # S0's +10000% is clipped to the 99th pct of the cross-section,
        # so no quintile can book the raw error
        self.assertLess(res.quantile_returns["Q1"].iloc[0], 50.0)

    def test_none_disables(self):
        dates = pd.date_range("2020-01-01", periods=4, freq="D")
        cols = [f"S{i}" for i in range(10)]
        prices = pd.DataFrame(100.0, index=dates, columns=cols)
        prices.loc[dates[2]:, "S0"] = 200.0
        signals = pd.DataFrame(np.nan, index=dates, columns=cols)
        signals.loc[dates[0]] = np.arange(10.0)
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[dates[1]],
                             winsorize_hold=None)
        res = run_backtest(prices, signals.ffill(), cfg)
        self.assertAlmostEqual(res.quantile_returns["Q1"].iloc[0], 0.5)


class TestExitFill(unittest.TestCase):
    def _gap_panels(self):
        dates = pd.date_range("2020-01-01", periods=6, freq="D")
        cols = ["A", "B", "C", "D", "E"]
        prices = pd.DataFrame(100.0, index=dates, columns=cols)
        # C: gap (missing day 3-4, back day 5); D: permanently gone at day 3
        prices.loc[dates[3]:dates[4], "C"] = np.nan
        prices.loc[dates[3]:, "D"] = np.nan
        signals = pd.DataFrame(np.nan, index=dates, columns=cols)
        signals.loc[dates[0]] = [1.0, 2.0, 5.0, 4.0, 3.0]  # C top, D 2nd
        return prices, signals

    def test_gap_books_zero_permanent_books_fill(self):
        prices, signals = self._gap_panels()
        idx = prices.index
        exit_fill = pd.DataFrame(np.nan, index=idx, columns=prices.columns)
        # first period exits at idx[3]: C gappy, D permanently gone
        exit_fill.loc[idx[3], "C"] = 0.0    # gap
        exit_fill.loc[idx[3], "D"] = -0.3   # permanent
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[idx[1], idx[3]],
                             delist_fill=-1.0, exit_fill=exit_fill)
        res = run_backtest(prices, signals.ffill(), cfg)
        # Q5 holds only C (gap -> 0.0); Q4 holds only D (-0.3)
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], 0.0)
        self.assertAlmostEqual(res.quantile_returns["Q4"].iloc[0], -0.3)

    def test_exit_fill_falls_back_to_delist_fill(self):
        prices, signals = self._gap_panels()
        idx = prices.index
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[idx[1], idx[3]],
                             delist_fill=-1.0, exit_fill=None)
        res = run_backtest(prices, signals.ffill(), cfg)
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], -1.0)


class TestSpreadCostAccounting(unittest.TestCase):
    def test_both_legs_pay(self):
        dates = pd.date_range("2020-01-01", periods=4, freq="D")
        cols = [f"S{i}" for i in range(10)]
        prices = pd.DataFrame(100.0, index=dates, columns=cols)
        prices.loc[dates[2]:, "S9"] = 110.0  # top quintile +10%
        prices.loc[dates[2]:, "S0"] = 90.0   # bottom quintile -10%
        signals = pd.DataFrame(np.nan, index=dates, columns=cols)
        signals.loc[dates[0]] = np.arange(10.0)
        sig = signals.ffill()
        gross = run_backtest(prices, sig,
                             BacktestConfig(n_quantiles=5, signal_lag=1,
                                            cost_bps=0.0,
                                            rebalance_dates=[dates[1]]))
        net = run_backtest(prices, sig,
                           BacktestConfig(n_quantiles=5, signal_lag=1,
                                          cost_bps=100.0,  # 1% one-way
                                          rebalance_dates=[dates[1]]))
        summ = pb.summarize_spread(gross, net, 100.0)
        # gross spread = 0.05 - (-0.05) = 0.10; each leg turns over 0.5
        # (from flat, 0.5*|w|_1) -> cost 2 * 0.5 * 1% = 0.01; net = 0.09
        self.assertAlmostEqual(summ["ann_return"], 0.09 * 12, places=6)


class TestTradeCalendar(unittest.TestCase):
    def test_month_end_plus_one(self):
        dates = pd.DatetimeIndex([pd.Timestamp("2020-01-30"),
                                  pd.Timestamp("2020-01-31"),
                                  pd.Timestamp("2020-02-03"),
                                  pd.Timestamp("2020-02-28"),
                                  pd.Timestamp("2020-03-02"),
                                  pd.Timestamp("2020-03-31"),
                                  pd.Timestamp("2020-04-01")])
        me = [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-28"),
              pd.Timestamp("2020-03-31")]
        trades = pb.trade_calendar(list(dates), me)
        # 2020-03-31 + 1 has no following trade date -> dropped
        self.assertEqual(list(trades),
                         [pd.Timestamp("2020-02-03"),
                          pd.Timestamp("2020-03-02")])


if __name__ == "__main__":
    unittest.main()
