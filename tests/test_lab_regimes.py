"""Tests for market-regime conditioning (synthetic data only)."""
import unittest

import numpy as np
import pandas as pd

from borealis.lab import regimes


def _spy_prices():
    # 300 trading days; first 150 drift up, next 150 drift down;
    # second half twice as volatile
    rng = np.random.default_rng(11)
    up = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.005, 150)))
    dn = up[-1] * np.exp(np.cumsum(rng.normal(-0.002, 0.010, 150)))
    px = np.concatenate([up, dn])
    idx = pd.bdate_range("2020-01-01", periods=300)
    return pd.DataFrame({"SPY": px}, index=idx)


class TestSpyRegimes(unittest.TestCase):
    def test_up_down_and_vol_split(self):
        prices = _spy_prices()
        sig_dates = list(prices.index[63::21])  # monthly-ish grid
        reg = regimes.spy_regimes(prices, sig_dates)
        self.assertGreaterEqual(
            set(reg.columns),
            {"mkt_ret_21d", "mkt_up", "spy_vol_63d", "high_vol"})
        # early dates (uptrend) mostly up, late dates (downtrend) mostly down
        self.assertGreater(reg["mkt_up"].iloc[:4].mean(), 0.5)
        self.assertLess(reg["mkt_up"].iloc[-4:].mean(), 0.5)
        # high-vol bucket is the more volatile half by construction
        self.assertGreater(
            reg.loc[reg["high_vol"], "spy_vol_63d"].mean(),
            reg.loc[~reg["high_vol"], "spy_vol_63d"].mean())
        # median split -> roughly half the dates in each bucket
        self.assertGreater(reg["high_vol"].mean(), 0.3)
        self.assertLess(reg["high_vol"].mean(), 0.7)

    def test_missing_spy_raises(self):
        prices = pd.DataFrame({"AAA": [1.0, 2.0, 3.0]},
                              index=pd.bdate_range("2020-01-01", periods=3))
        with self.assertRaises(KeyError):
            regimes.spy_regimes(prices, list(prices.index))


class TestIcByRegime(unittest.TestCase):
    def test_splits_correctly(self):
        idx = pd.date_range("2021-01-31", periods=10, freq="M")
        ics = pd.Series([0.04, 0.05, 0.06, 0.045, 0.055,
                         -0.02, -0.01, -0.015, -0.005, -0.012], index=idx)
        reg = pd.DataFrame({"mkt_up": [True] * 5 + [False] * 5,
                            "high_vol": [False] * 5 + [True] * 5}, index=idx)
        out = regimes.ic_by_regime(ics, reg)
        self.assertAlmostEqual(out["mkt_up"]["up"]["mean"], 0.05)
        self.assertAlmostEqual(out["mkt_up"]["down"]["mean"], -0.0124)
        self.assertEqual(out["mkt_up"]["up"]["n"], 5)
        self.assertAlmostEqual(out["high_vol"]["high_vol"]["mean"], -0.0124)
        self.assertTrue(np.isfinite(out["mkt_up"]["diff_tstat"]))


if __name__ == "__main__":
    unittest.main()
