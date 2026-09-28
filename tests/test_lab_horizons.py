"""Tests for IC decay across forward-return horizons (synthetic data)."""
import unittest

import numpy as np
import pandas as pd

from borealis.lab import horizons


def _prices(n_days=400, n_tickers=50, seed=3):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0005, 0.01, size=(n_days, n_tickers))
    px = 100 * np.exp(np.cumsum(rets, axis=0))
    idx = pd.bdate_range("2020-01-01", periods=n_days)
    cols = [f"T{i:03d}" for i in range(n_tickers)]
    return pd.DataFrame(px, index=idx, columns=cols)


class TestForwardReturns(unittest.TestCase):
    def test_matches_known_move(self):
        px = _prices()
        sig_dates = [px.index[100]]
        fwd = horizons.forward_returns(px, sig_dates, horizons=(21,))
        self.assertEqual(len(fwd), 50)
        t = px.index[100]
        expect = px.loc[px.index[121], "T007"] / px.loc[t, "T007"] - 1.0
        got = fwd.loc[(fwd["date"] == t) & (fwd["ticker"] == "T007"),
                      "fwd_ret"].iloc[0]
        self.assertEqual(got, expect)

    def test_truncates_at_sample_end(self):
        px = _prices(n_days=100)
        sig_dates = [px.index[90]]  # only 10 days left: 21d impossible
        fwd = horizons.forward_returns(px, sig_dates, horizons=(21, 63))
        self.assertTrue(fwd.empty)


class TestIcAtHorizons(unittest.TestCase):
    def test_perfect_signal(self):
        px = _prices()
        sig_dates = list(px.index[::21][:10])
        # signal = rank of the realized 21d forward return -> IC ~ +1
        fwd = horizons.forward_returns(px, sig_dates, horizons=(21, 63))
        sig_rows = []
        for d in sig_dates:
            g = fwd[(fwd["date"] == d) & (fwd["h"] == 21)]
            r = g.set_index("ticker")["fwd_ret"].rank()
            for t, v in r.items():
                sig_rows.append({"date": d, "ticker": t, "sleeve_x": v})
        sig = pd.DataFrame(sig_rows)
        out = horizons.ic_at_horizons(sig, fwd, ["x"])
        self.assertGreater(out["x"][21]["mean"], 0.99)
        self.assertEqual(out["x"][21]["n"], 10)


class TestIcHalfLife(unittest.TestCase):
    def test_interpolation_and_censoring(self):
        # crosses half between 63 and 126
        hl = horizons.ic_half_life({21: 0.08, 63: 0.05, 126: 0.03, 252: 0.02})
        self.assertIsNone(hl["censored"])
        self.assertGreater(hl["days"], 63)
        self.assertLess(hl["days"], 126)
        # never crosses -> censored at max horizon
        hl2 = horizons.ic_half_life({21: 0.08, 63: 0.07,
                                      126: 0.06, 252: 0.05})
        self.assertEqual(hl2["days"], 252)
        self.assertEqual(hl2["censored"], "above-half-at-max-horizon")
        # nonpositive base IC -> undefined
        hl3 = horizons.ic_half_life({21: -0.01, 63: 0.02})
        self.assertIsNone(hl3["days"])

    def test_exact_interpolation(self):
        # 0.08 -> 0.04 linearly between 21 and 63: half of 0.08 hit at 63
        hl = horizons.ic_half_life({21: 0.08, 63: 0.04})
        self.assertEqual(hl["days"], 63)
        self.assertIsNone(hl["censored"])


if __name__ == "__main__":
    unittest.main()
