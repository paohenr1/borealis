"""Tests for factor modules: orientation and graceful degradation."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.factors import quality, growth, momentum, lowvol, size, value


def _toy():
    return pd.DataFrame({
        "sector": ["s"] * 4,
        "sales_growth_q": [0.05, -0.02, 0.10, np.nan],
        "pct_above_52w_low": [0.1, 0.5, 0.3, 0.2],
        "trailing_beta": [1.5, 0.5, 1.0, 1.2],
    })


class TestQuality(unittest.TestCase):
    def test_missing_metrics_warn_and_nan(self):
        with self.assertWarns(UserWarning):
            q = quality.quality_score(_toy())
        self.assertTrue(q.isna().all())

    def test_present_metrics_oriented(self):
        df = _toy()
        df["roe"] = [0.20, 0.05, 0.15, 0.10]          # higher better
        df["debt_to_equity"] = [0.2, 2.0, 0.5, 1.0]  # lower better
        df["interest_coverage"] = [8.0, 1.5, 5.0, 3.0]  # higher better
        q = quality.quality_score(df)
        self.assertGreater(q.iloc[0], q.iloc[1])


class TestSize(unittest.TestCase):
    def test_larger_is_better(self):
        df = pd.DataFrame({
            "sector": ["s"] * 3,
            "enterprise_value": [1e9, 1e11, 1e10],
        })
        s = size.size_score(df)
        self.assertGreater(s.iloc[1], s.iloc[2])
        self.assertGreater(s.iloc[2], s.iloc[0])

    def test_log_transform(self):
        df = pd.DataFrame({
            "sector": ["s"] * 2,
            "enterprise_value": [np.e, np.e ** 2],
        })
        s = size.size_score(df)
        # log-spaced EVs must come out exactly 1.0 apart before z-scoring
        self.assertAlmostEqual(s.iloc[1] - s.iloc[0], 1.0)

    def test_nonpositive_ev_imputed_not_ranked(self):
        df = pd.DataFrame({
            "sector": ["s"] * 3,
            "enterprise_value": [1e9, -5e8, 0.0],
        })
        s = size.size_score(df)
        self.assertFalse(s.isna().any())  # quarantined, sector median imputed
        self.assertEqual(s.iloc[1], s.iloc[2])  # both imputed identically


class TestGrowthRetest(unittest.TestCase):
    def test_prefers_ttm_lab_definitions(self):
        df = pd.DataFrame({
            "sector": ["s"] * 3,
            "rev_growth": [0.10, 0.02, 0.05],
            "ebit_growth": [0.20, 0.01, 0.10],
            "ebitda_growth": [0.15, 0.03, 0.08],
            "sales_growth_q": [0.01, 0.50, 0.02],  # must be ignored
        })
        g = growth.growth_score(df)
        self.assertGreater(g.iloc[0], g.iloc[1])

    def test_workbook_quarterly_fallback(self):
        df = pd.DataFrame({
            "sector": ["s"] * 3,
            "sales_growth_q": [0.10, -0.05, 0.02],
            "eps_growth_q": [0.20, -0.10, 0.05],
        })
        g = growth.growth_score(df)
        self.assertGreater(g.iloc[0], g.iloc[1])
        self.assertFalse(g.isna().any())

    def test_no_growth_data_gives_nan(self):
        g = growth.growth_score(pd.DataFrame({"sector": ["s"]}))
        self.assertTrue(g.isna().all())


class TestOrientation(unittest.TestCase):
    def test_growth_higher_better(self):
        g = growth.growth_score(_toy())
        self.assertGreater(g.iloc[2], g.iloc[1])

    def test_momentum_higher_better(self):
        m = momentum.momentum_score(_toy())
        self.assertGreater(m.iloc[1], m.iloc[0])

    def test_lowvol_lower_beta_better(self):
        v = lowvol.lowvol_score(_toy())
        self.assertGreater(v.iloc[1], v.iloc[0])  # beta 0.5 beats 1.5

    def test_nan_imputed_not_dropped(self):
        g = growth.growth_score(_toy())
        self.assertFalse(g.isna().any())


class TestValueEarningsYield(unittest.TestCase):
    """2026-09-30: P/E replaced by earnings yield in the value sleeve."""

    def _df(self):
        return pd.DataFrame({
            "sector": ["s"] * 4,
            "earn_yield": [0.10, 0.02, 0.05, np.nan],
            "ps_ratio": [1.0, 5.0, 2.0, 3.0],
            "ev_to_ebitda": [8.0, 20.0, 12.0, 15.0],
            "pb_ratio": [1.5, 4.0, 2.0, 2.5],
            "pe_ratio": [10.0, 50.0, 20.0, 30.0],  # diagnostic only now
        })

    def test_earnings_yield_in_sleeve_pe_out(self):
        self.assertIn("earn_yield", value.VALUE_METRICS)
        self.assertNotIn("pe_ratio", value.VALUE_METRICS)

    def test_higher_ey_is_cheaper(self):
        v = value.value_score(self._df())
        self.assertGreater(v.iloc[0], v.iloc[1])  # EY 10% beats 2%

    def test_negative_ey_kept_not_quarantined(self):
        # a negative earnings yield is informative (unlike negative P/E)
        df = pd.DataFrame({
            "sector": ["s"] * 3,
            "earn_yield": [0.10, -0.05, 0.02],
        })
        v = value.value_score(df)
        self.assertFalse(v.isna().any())
        self.assertLess(v.iloc[1], v.iloc[2])  # -5% EY ranks below +2%

    def test_workbook_path_derives_ey_from_pe(self):
        # no earn_yield column -> derive 1/pe_ratio with the same quarantine
        df = pd.DataFrame({
            "sector": ["s"] * 3,
            "pe_ratio": [10.0, 50.0, -5.0],
        })
        v = value.value_score(df)
        self.assertFalse(v.isna().any())
        self.assertGreater(v.iloc[0], v.iloc[1])  # EY 10% beats 2%


class TestLowvolRealizedVol(unittest.TestCase):
    """2026-09-30: live low-vol reverted to 126d realized volatility."""

    def test_prefers_vol_126d_over_beta(self):
        df = pd.DataFrame({
            "sector": ["s"] * 3,
            "vol_126d": [0.40, 0.15, 0.25],
            "trailing_beta": [0.5, 1.5, 1.0],  # disagrees on purpose
        })
        v = lowvol.lowvol_score(df)
        self.assertGreater(v.iloc[1], v.iloc[0])  # vol 0.15 beats 0.40

    def test_workbook_fallback_to_beta(self):
        df = pd.DataFrame({
            "sector": ["s"] * 3,
            "trailing_beta": [1.5, 0.5, 1.0],
        })
        v = lowvol.lowvol_score(df)
        self.assertGreater(v.iloc[1], v.iloc[0])


if __name__ == "__main__":
    unittest.main()
