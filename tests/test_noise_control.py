"""Tests for the 2026-09-30 zero-weight sleeve taxonomy.

Three distinct zero-weight categories:
- diagnostics (quality, size): scored every run, written reinstatement rule;
- falsified belief (growth): popular belief, tested and rejected, kept
  scored for transparency -- NOT a candidate, NO reinstatement rule;
- negative control (noise): seeded Gaussian, null by construction; if it
  ever clears |t| > 2 the lab machinery is broken, not the market.
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.factors import noise
from borealis.lab import composite as lab_composite
from borealis.lab import preprocess
from borealis.scoring import composite as scoring_composite

REPO = Path(__file__).resolve().parents[1]


def _toy_live(n=6, date="2026-09-30"):
    tickers = [f"T{i}" for i in range(n)]
    return pd.DataFrame({
        "ticker": tickers,
        "sector": ["s"] * n,
        "date": [date] * n,
        "value": np.linspace(-1, 1, n),
        "momentum": np.linspace(1, -1, n),
        "lowvol": np.linspace(-0.5, 0.5, n),
    })


class TestNoiseDeterminism(unittest.TestCase):
    def test_same_date_twice_identical(self):
        df = _toy_live()
        a = noise.noise_score(df, seed_key="2026-09-30")
        b = noise.noise_score(df, seed_key="2026-09-30")
        pd.testing.assert_series_equal(a, b)

    def test_different_dates_differ(self):
        df = _toy_live()
        a = noise.noise_score(df, seed_key="2026-09-30")
        b = noise.noise_score(df, seed_key="2026-08-31")
        self.assertFalse(a.equals(b))
        # overwhelmingly likely to differ in every position for n=6
        self.assertGreater((a != b).sum(), 0)

    def test_date_column_used_when_present(self):
        df = _toy_live(date="2026-09-30")
        a = noise.noise_score(df)  # no seed_key: falls back to date column
        b = noise.noise_score(df, seed_key="2026-09-30")
        pd.testing.assert_series_equal(a, b)

    def test_tickers_differ_within_date(self):
        # A degenerate cross-section (all tickers same value) would z-score
        # to NaN; every ticker must get its own draw.
        s = noise.noise_score(_toy_live(n=20), seed_key="2026-09-30")
        self.assertEqual(s.nunique(), 20)

    def test_empty_frame(self):
        df = _toy_live(n=0)
        s = noise.noise_score(df, seed_key="2026-09-30")
        self.assertEqual(len(s), 0)

    def test_add_noise_raw(self):
        frame = pd.DataFrame({
            "date": pd.to_datetime(["2026-09-30", "2026-09-30", "2026-08-31"]),
            "ticker": ["A", "B", "A"],
        })
        out = noise.add_noise_raw(frame)
        self.assertIn("noise_raw", out.columns)
        self.assertTrue(out["noise_raw"].notna().all())
        # same (date, ticker) -> same value across calls
        out2 = noise.add_noise_raw(frame)
        pd.testing.assert_series_equal(out["noise_raw"], out2["noise_raw"])


class TestNoiseNullIC(unittest.TestCase):
    def test_ic_insignificant_on_synthetic_data(self):
        # Fully deterministic: seeded noise vs independent seeded returns.
        # The null must not clear significance.
        rng = np.random.default_rng(7)
        dates = pd.date_range("2020-01-31", periods=120, freq="ME")
        rows = []
        for d in dates:
            tickers = [f"T{i:03d}" for i in range(60)]
            rows.append(pd.DataFrame({
                "date": d, "ticker": tickers,
                "sector": ["s"] * 60,
                "fwd_ret": rng.standard_normal(60),
            }))
        frame = pd.concat(rows, ignore_index=True)
        frame = noise.add_noise_raw(frame)
        frame = preprocess.add_lab_zscores(frame, ["noise_raw"])
        ics = []
        for d, g in frame.groupby("date"):
            z = g["z_noise_raw"].to_numpy()
            r = g["fwd_ret"].to_numpy()
            ics.append(pd.Series(z).corr(pd.Series(r), method="spearman"))
        ics = np.array(ics)
        t = ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics)))
        self.assertLess(abs(t), 2.0, f"noise IC t-stat {t:.2f} cleared 2")


class TestConfigTaxonomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load(open(REPO / "config" / "factors.yaml"))

    def test_noise_zero_weight_negative_control(self):
        n = self.cfg["factors"]["noise"]
        self.assertEqual(n["weight"], 0.0)
        self.assertIn("negative control", n["description"].lower())
        self.assertIn("null by construction", n["description"].lower())

    def test_growth_zero_weight_falsified_belief(self):
        g = self.cfg["factors"]["growth"]
        self.assertEqual(g["weight"], 0.0)
        desc = g["description"].lower()
        self.assertIn("falsified", desc)
        # growth is explicitly NOT the negative control anymore
        self.assertIn("not a negative control", desc)
        self.assertIn("no reinstatement", desc)

    def test_live_weights_unchanged(self):
        w = {f: c["weight"] for f, c in self.cfg["factors"].items()}
        self.assertEqual(w["value"], 0.20)
        self.assertEqual(w["momentum"], 0.20)
        self.assertEqual(w["lowvol"], 0.10)
        self.assertEqual(w["quality"], 0.00)
        self.assertEqual(w["size"], 0.00)


class TestLabWiring(unittest.TestCase):
    def test_noise_in_sleeves_with_direction(self):
        self.assertEqual(preprocess.SLEEVES["noise"], ["noise_raw"])
        self.assertIn("noise_raw", preprocess.FACTOR_DIRECTION)

    def test_noise_zero_weight_in_lab(self):
        self.assertEqual(lab_composite.SLEEVE_WEIGHTS["noise"], 0.00)

    def test_sleeve_zscores_emits_noise(self):
        frame = pd.DataFrame({
            "date": pd.to_datetime(["2026-09-30"] * 4),
            "ticker": ["A", "B", "C", "D"],
            "sector": ["s"] * 4,
        })
        frame = noise.add_noise_raw(frame)
        frame = preprocess.add_lab_zscores(frame, ["noise_raw"])
        sz = lab_composite.sleeve_zscores(frame)
        self.assertIn("sleeve_noise", sz.columns)
        self.assertTrue(sz["sleeve_noise"].notna().all())

    def test_composite_ignores_noise(self):
        frame = pd.DataFrame({
            "date": pd.to_datetime(["2026-09-30"] * 4),
            "ticker": ["A", "B", "C", "D"],
            "sector": ["s"] * 4,
        })
        frame = noise.add_noise_raw(frame)
        frame = preprocess.add_lab_zscores(frame, ["noise_raw"])
        comp = lab_composite.composite_zscore(frame)
        # noise (and other zero-weight sleeves) contribute nothing; only
        # value/momentum/lowvol are absent here -> all-NaN composite
        self.assertTrue(comp.isna().all())


class TestCompositeUnchanged(unittest.TestCase):
    def test_noise_contributes_nothing_live(self):
        weights = {"value": 0.20, "momentum": 0.20, "lowvol": 0.10,
                   "quality": 0.00, "size": 0.00, "growth": 0.00,
                   "noise": 0.00}
        df = _toy_live(n=12)
        df["noise"] = noise.noise_score(df, seed_key="2026-09-30")
        with_noise = scoring_composite.composite_score(df, weights)
        without = scoring_composite.composite_score(df.drop(columns=["noise"]),
                                                    weights)
        pd.testing.assert_series_equal(with_noise["composite"],
                                       without["composite"])

    def test_effective_weights_still_40_40_20(self):
        weights = {"value": 0.20, "momentum": 0.20, "lowvol": 0.10,
                   "noise": 0.00}
        df = _toy_live(n=12)
        df["noise"] = noise.noise_score(df, seed_key="2026-09-30")
        out = scoring_composite.composite_score(df, weights)
        for col in ("value", "momentum", "lowvol", "noise"):
            z = scoring_composite.sector_zscore(df, col).fillna(0.0)
            out[f"manual_z_{col}"] = z
        expected = (0.40 * out["manual_z_value"]
                    + 0.40 * out["manual_z_momentum"]
                    + 0.20 * out["manual_z_lowvol"])
        pd.testing.assert_series_equal(out["composite"], expected,
                                       check_names=False)


if __name__ == "__main__":
    unittest.main()
