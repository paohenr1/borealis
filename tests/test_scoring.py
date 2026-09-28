"""Tests for scoring: winsorization, sector neutrality, zero-ratio quarantine."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.factors.value import value_score
from borealis.scoring.composite import winsorize, sector_zscore, composite_score


def _toy():
    return pd.DataFrame({
        "ticker": ["A", "B", "C", "D", "E", "F"],
        "sector": ["tech", "tech", "tech", "bank", "bank", "bank"],
        "pe_ratio": [10.0, 15.0, 0.0, 8.0, -5.0, 12.0],   # 0 and negative = not cheap
        "ps_ratio": [1.0, 2.0, 1.5, 0.8, 0.9, 1.1],
        "peg_ratio": [1.0, 1.2, 0.0, 0.9, 1.0, 1.1],
        "value": [0.0] * 6,
    })


class TestWinsorize(unittest.TestCase):
    def test_clips_outliers(self):
        s = pd.Series([1.0] * 10 + [1000.0])
        w = winsorize(s, sigma=3.0)
        self.assertLess(w.max(), 1000.0)
        self.assertEqual(len(w), len(s))

    def test_no_dispersion_passthrough(self):
        s = pd.Series([5.0, 5.0, 5.0])
        pd.testing.assert_series_equal(winsorize(s), s)


class TestSectorZscore(unittest.TestCase):
    def test_neutral_within_sector(self):
        df = pd.DataFrame({
            "sector": ["a"] * 20 + ["b"] * 20,
            "x": list(range(20)) + list(range(100, 120)),
        })
        z = sector_zscore(df, "x")
        for sec in ["a", "b"]:
            self.assertAlmostEqual(z[df["sector"] == sec].mean(), 0.0, places=9)


class TestValueFactor(unittest.TestCase):
    def test_zero_pe_is_not_cheapest(self):
        df = _toy()
        scores = value_score(df)
        # C has pe_ratio == 0 -> quarantined; must NOT outrank A (pe 10, cheapest valid)
        self.assertLess(scores.loc[2], scores.loc[0])

    def test_negative_pe_is_not_cheapest(self):
        df = _toy()
        scores = value_score(df)
        self.assertLess(scores.loc[4], scores.loc[3])


class TestComposite(unittest.TestCase):
    def test_rank_one_is_most_attractive_per_sector(self):
        df = _toy()
        df["value"] = value_score(df)
        out = composite_score(df, {"value": 1.0})
        for sec, grp in out.groupby("sector"):
            best = grp.loc[grp["composite"].idxmax()]
            self.assertEqual(best["rank"], 1)

    def test_all_nan_factor_skipped(self):
        df = _toy()
        df["value"] = value_score(df)
        df["quality"] = np.nan
        out = composite_score(df, {"value": 0.5, "quality": 0.5})
        self.assertIn("composite", out.columns)
        self.assertNotIn("z_quality", out.columns)


if __name__ == "__main__":
    unittest.main()
