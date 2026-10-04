"""Tests for per-sleeve costed backtests (synthetic data only)."""
import unittest

import numpy as np
import pandas as pd

from borealis.backtest.engine import BacktestResult
from borealis.lab import sleeve_backtest as sb


def _sig_frame():
    dates = [pd.Timestamp("2021-01-31"), pd.Timestamp("2021-02-28")]
    rows = []
    for d in dates:
        for t in ["A", "B", "C", "D", "E", "F"]:
            rows.append({"date": d, "ticker": t,
                         "sleeve_value": float(ord(t)),
                         "sleeve_quality": float(ord(t)) * 2.0})
    return pd.DataFrame(rows)


class TestSleeveSignalMatrix(unittest.TestCase):
    def test_pivots_and_ffills(self):
        frame = _sig_frame()
        px_idx = pd.DatetimeIndex([pd.Timestamp("2021-01-31"),
                                   pd.Timestamp("2021-02-01"),
                                   pd.Timestamp("2021-02-28"),
                                   pd.Timestamp("2021-03-01")])
        m = sb.sleeve_signal_matrix(frame, "value", px_idx)
        self.assertEqual(list(m.index), list(px_idx))
        # month-end signal carried forward to the next trading day
        self.assertEqual(m.loc["2021-02-01", "A"], float(ord("A")))
        self.assertEqual(m.loc["2021-03-01", "F"], float(ord("F")))

    def test_unknown_sleeve_is_all_nan(self):
        frame = _sig_frame()
        px_idx = pd.DatetimeIndex([pd.Timestamp("2021-01-31")])
        m = sb.sleeve_signal_matrix(frame, "nope", px_idx)
        self.assertTrue(m.isna().all().all())


def _fake_result(q1=0.01, q3=0.02, q5=0.03, n=12):
    idx = pd.date_range("2021-01-31", periods=n, freq="ME")
    qret = pd.DataFrame({"Q1": np.full(n, q1), "Q2": 0.0,
                         "Q3": np.full(n, q3), "Q4": 0.0,
                         "Q5": np.full(n, q5)}, index=idx)
    turn = pd.DataFrame(np.full((n, 5), 0.2), index=idx,
                        columns=["Q1", "Q2", "Q3", "Q4", "Q5"])
    stats = pd.DataFrame(index=["Q1", "Q2", "Q3", "Q4", "Q5"])
    return BacktestResult(qret, turn, stats)


class TestSleeveSpreadReport(unittest.TestCase):
    def test_decomposition(self):
        runs = {"value": {0.0: _fake_result(), 10.0: _fake_result()}}
        rep = sb.sleeve_spread_report(runs, cost=10.0)
        r = rep.loc["value"]
        # gross spread 0.02/mo; turnover cost (0.2+0.2)*10bps = 0.0004/mo
        self.assertAlmostEqual(r["ann_return"], (0.02 - 0.0004) * 12)
        self.assertAlmostEqual(r["q1_ann"], 0.01 * 12)
        self.assertAlmostEqual(r["q5_ann"], 0.03 * 12)
        # long_contrib = q5-q3, short_contrib = q3-q1
        self.assertAlmostEqual(r["long_contrib"], 0.01 * 12)
        self.assertAlmostEqual(r["short_contrib"], 0.01 * 12)
        self.assertAlmostEqual(r["short_share"], 0.5)
        self.assertAlmostEqual(r["avg_turnover_ls"], 0.4)

    def test_short_share_nan_when_no_spread(self):
        runs = {"flat": {0.0: _fake_result(q1=0.02, q3=0.02, q5=0.02),
                         10.0: _fake_result(q1=0.02, q3=0.02, q5=0.02)}}
        rep = sb.sleeve_spread_report(runs, cost=10.0)
        self.assertTrue(np.isnan(rep.loc["flat", "short_share"]))


if __name__ == "__main__":
    unittest.main()
