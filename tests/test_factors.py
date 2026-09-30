"""Tests for factor modules: orientation and graceful degradation."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.factors import quality, growth, momentum, lowvol, size


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


if __name__ == "__main__":
    unittest.main()
