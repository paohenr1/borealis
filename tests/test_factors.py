"""Tests for factor modules: orientation and graceful degradation."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.factors import quality, growth, momentum, lowvol


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
        q = quality.quality_score(df)
        self.assertGreater(q.iloc[0], q.iloc[1])


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
