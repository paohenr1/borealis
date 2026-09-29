"""Tests for the live Intrinio-backed universe (synthetic zips + universe csv)."""
import shutil
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.ingest import universe_live
from borealis.ingest.loader import ORDERED_COLS

REPO = Path(__file__).resolve().parents[1]
UNIVERSE_CSV = REPO / "data" / "raw" / "universe_520.csv"


def _write_zip(path: Path, rows: list[dict], inner: str):
    df = pd.DataFrame(rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(inner, df.to_csv(index=False))


def _companies_rows():
    return [
        {"TICKER": "AAA", "NAME": "Alpha Inc",
         "INDUSTRY_GROUP_NAME": "Computer & Office Equipment"},
        {"TICKER": "BBB", "NAME": "Beta Corp",
         "INDUSTRY_GROUP_NAME": "Pharmaceutical Preparations"},
        {"TICKER": "CCC", "NAME": "Gamma LLC",
         "INDUSTRY_GROUP_NAME": "Telephone Communications"},
        {"TICKER": "NOPRICE", "NAME": "No Price Co",
         "INDUSTRY_GROUP_NAME": "Crude Petroleum & Natural Gas"},
    ]


def _price_rows():
    rows = []
    for t, px in [("AAA", 100.0), ("BBB", 50.0), ("CCC", 200.0)]:
        rows.append({"TICKER": t, "DATE": "2026-09-28", "CLOSE": px,
                     "FIFTY_TWO_WEEK_HIGH": px * 1.25, "FIFTY_TWO_WEEK_LOW": px * 0.8})
        rows.append({"TICKER": t, "DATE": "2026-09-25", "CLOSE": px * 0.99,
                     "FIFTY_TWO_WEEK_HIGH": px * 1.25, "FIFTY_TWO_WEEK_LOW": px * 0.8})
    return rows


def _calc_rows():
    return [
        {"ticker": "AAA", "filing_date": "2026-09-20", "first_calculable_at": "2026-09-21",
         "fiscal_period": "Q2TTM", "fiscal_year": 2026, "marketcap": 1e9,
         "pricetoearnings": 20.0, "pricetorevenue": 4.0, "peg_ratio": 1.5,
         "roe": 0.18, "freecashflow": 1e8, "totalrevenue": 5e8,
         "revenuegrowth": 0.12, "beta": 1.1, "debttoequity": 0.5},
        {"ticker": "BBB", "filing_date": "2026-09-20", "first_calculable_at": "2026-09-21",
         "fiscal_period": "Q2TTM", "fiscal_year": 2026, "marketcap": 2e9,
         "pricetoearnings": 25.0, "pricetorevenue": 5.0, "peg_ratio": 2.0,
         "roe": 0.10, "freecashflow": 5e7, "totalrevenue": 5e8,
         "revenuegrowth": 0.05, "beta": 0.9, "debttoequity": 1.2},
        # older vintage for CCC must lose to the newer one
        {"ticker": "CCC", "filing_date": "2026-06-20", "first_calculable_at": "2026-06-21",
         "fiscal_period": "Q1TTM", "fiscal_year": 2026, "marketcap": 3e9,
         "pricetoearnings": 30.0, "pricetorevenue": 6.0, "peg_ratio": 2.5,
         "roe": 0.05, "freecashflow": 1e7, "totalrevenue": 5e8,
         "revenuegrowth": 0.01, "beta": 1.3, "debttoequity": 2.0},
        {"ticker": "CCC", "filing_date": "2026-09-20", "first_calculable_at": "2026-09-21",
         "fiscal_period": "Q2TTM", "fiscal_year": 2026, "marketcap": 3.2e9,
         "pricetoearnings": 28.0, "pricetorevenue": 5.5, "peg_ratio": 2.2,
         "roe": 0.06, "freecashflow": 2e7, "totalrevenue": 5e8,
         "revenuegrowth": 0.03, "beta": 1.2, "debttoequity": 1.8},
    ]


def _income_rows():
    rows = []
    # (ticker, year, q, revenue)
    data = [
        ("AAA", 2025, "Q3", 1.1e8), ("AAA", 2025, "Q4", 1.2e8),
        ("AAA", 2026, "Q1", 1.0e8), ("AAA", 2026, "Q2", 1.2e8),
        ("AAA", 2025, "Q2", 1.0e8),
        ("BBB", 2025, "Q3", 1.8e8), ("BBB", 2025, "Q4", 1.9e8),
        ("BBB", 2026, "Q1", 2.0e8), ("BBB", 2026, "Q2", 2.1e8),
        ("BBB", 2025, "Q2", 1.9e8),
        # CCC: only 2 quarters -> YoY ok, TTM revenue NaN
        ("CCC", 2026, "Q2", 3.0e8), ("CCC", 2025, "Q2", 2.9e8),
    ]
    for t, y, q, rev in data:
        rows.append({"ticker": t, "fiscal_year": y, "fiscal_period": q,
                     "totalrevenue": rev})
    return rows


def _small_universe_df():
    return pd.DataFrame({
        "ticker": ["AAA", "BBB", "CCC", "NOPRICE"],
        "index_membership": ["SP500", "NASDAQ100", "DOW", "SP500"],
    })


class TestUniverseCsv(unittest.TestCase):
    def test_shape_and_membership(self):
        df = pd.read_csv(UNIVERSE_CSV, dtype=str)
        self.assertEqual(list(df.columns), ["ticker", "index_membership"])
        self.assertGreaterEqual(len(df), 515)
        self.assertLessEqual(len(df), 525)
        self.assertEqual(df["ticker"].nunique(), len(df))
        ok = {"SP500", "NASDAQ100", "DOW"}
        for m in df["index_membership"]:
            parts = set(m.split("|"))
            self.assertTrue(parts <= ok and parts, f"bad membership {m!r}")

    def test_known_overlaps(self):
        df = pd.read_csv(UNIVERSE_CSV, dtype=str).set_index("ticker")
        self.assertEqual(df.loc["NVDA", "index_membership"], "SP500|NASDAQ100|DOW")
        self.assertEqual(df.loc["MMM", "index_membership"], "SP500|DOW")
        self.assertEqual(df.loc["AAPL", "index_membership"], "SP500|NASDAQ100|DOW")


class TestSectorMap(unittest.TestCase):
    def test_industry_groups_map(self):
        expected = {
            "Computer & Office Equipment": "technology",
            "Pharmaceutical Preparations": "health_care",
            "National Commercial Banks": "financials",
            "Crude Petroleum & Natural Gas": "energy",
            "Air Transportation": "industrials",
            "Blast Furnaces & Steel Works": "materials",
            "Beverages": "consumer_staples",
            "Hotels & Motels": "consumer_discretionary",
            "Telephone Communications": "telecommunication",
            "Electric Services": "utilities",
            "REIT": "real_estate",
        }
        for raw, slug in expected.items():
            self.assertEqual(universe_live.map_sector(raw), slug)

    def test_all_live_universe_groups_mapped(self):
        # every industry group on a live-universe name must be in SECTOR_MAP
        import zipfile
        raw = (REPO / "data" / "raw" / "intrinio" / "2026-09-29")
        zf = raw / "companies.zip"
        if not zf.exists():
            self.skipTest("bulk data not downloaded")
        z = zipfile.ZipFile(zf)
        df = pd.read_csv(z.open("companies.csv"), low_memory=False,
                         usecols=["TICKER", "INDUSTRY_GROUP_NAME"])
        uni = set(pd.read_csv(UNIVERSE_CSV, dtype=str)["ticker"])
        uni |= {"BRK-B", "BF-A", "FOXA", "GOOGL", "NWSA", "MAAI"}
        groups = set(df[df["TICKER"].isin(uni)]["INDUSTRY_GROUP_NAME"].dropna())
        unmapped = groups - set(universe_live.SECTOR_MAP)
        self.assertEqual(unmapped, set(), f"unmapped groups: {unmapped}")

    def test_unmapped_raises(self):
        with self.assertRaises(ValueError):
            universe_live.map_sector("Quantum Services")

    def test_ticker_normalization(self):
        self.assertEqual(universe_live.bulk_ticker("BRK.B"), "BRK-B")
        self.assertEqual(universe_live.bulk_ticker("BF.B"), "BF-A")
        self.assertEqual(universe_live.bulk_ticker("FOX"), "FOXA")
        self.assertEqual(universe_live.bulk_ticker("GOOG"), "GOOGL")
        self.assertEqual(universe_live.bulk_ticker("NWS"), "NWSA")
        self.assertEqual(universe_live.bulk_ticker("MAA"), "MAAI")
        self.assertEqual(universe_live.bulk_ticker("AAPL"), "AAPL")


class TestBuildLiveUniverse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)
        _write_zip(self.raw / "companies_test.zip", _companies_rows(), "companies.csv")
        _write_zip(self.raw / "stock_prices_test.zip", _price_rows(), "prices.csv")
        _write_zip(self.raw / "US_TEST_CALCULATIONS.zip", _calc_rows(), "calc.csv")
        _write_zip(self.raw / "US_TEST_INCOME_STATEMENT.zip", _income_rows(), "inc.csv")

    def tearDown(self):
        self.tmp.cleanup()

    def _build(self):
        with patch.object(universe_live, "read_universe_csv",
                          return_value=_small_universe_df()):
            with self.assertWarns(UserWarning):  # NOPRICE excluded loudly
                return universe_live.build_live_universe("dummy.csv", self.raw)

    def test_workbook_compatible_columns_plus_quality(self):
        frame, _ = self._build()
        for col in ORDERED_COLS + ["sector_raw", "sector"]:
            self.assertIn(col, frame.columns)
        for col in ["roe", "fcf_margin", "debt_to_equity"]:
            self.assertIn(col, frame.columns)
        self.assertEqual(list(frame.columns),
                         [c for c in universe_live.LIVE_COLS if c in frame.columns])

    def test_every_row_has_price_and_sector(self):
        frame, _ = self._build()
        self.assertTrue(frame["price"].notna().all())
        self.assertTrue(frame["sector"].notna().all())
        self.assertFalse((frame["sector"] == "").any())

    def test_no_price_ticker_excluded_and_reported(self):
        frame, coverage = self._build()
        self.assertNotIn("NOPRICE", set(frame["ticker"]))
        self.assertIn("NOPRICE", coverage["excluded_no_price"])

    def test_latest_vintage_wins(self):
        frame, _ = self._build()
        ccc = frame.loc[frame["ticker"] == "CCC"].iloc[0]
        self.assertEqual(ccc["pe_ratio"], 28.0)   # newer vintage, not 30.0
        self.assertEqual(ccc["price"], 200.0)     # latest date, not 198.0
        self.assertAlmostEqual(ccc["pct_below_52w_high"], 200.0 / 250.0 - 1)
        self.assertAlmostEqual(ccc["pct_above_52w_low"], 200.0 / 160.0 - 1)

    def test_derived_metrics(self):
        frame, _ = self._build()
        aaa = frame.loc[frame["ticker"] == "AAA"].iloc[0]
        # TTM revenue = 1.1+1.2+1.0+1.2 = 4.5e8; YoY Q2: 1.2/1.0 - 1
        self.assertAlmostEqual(aaa["fcf_margin"], 1e8 / 4.5e8)
        self.assertAlmostEqual(aaa["sales_growth_q"], 0.2)
        self.assertEqual(aaa["debt_to_equity"], 0.5)
        self.assertEqual(aaa["last_qtr"], "Q2 2026")
        self.assertEqual(aaa["currency"], "USD")
        self.assertEqual(aaa["sector"], "technology")
        self.assertEqual(aaa["sector_raw"], "Computer & Office Equipment")
        ccc = frame.loc[frame["ticker"] == "CCC"].iloc[0]
        # Communication Services -> telecommunication (documented choice)
        self.assertEqual(ccc["sector"], "telecommunication")
        # only 2 quarterlies -> TTM revenue NaN -> fcf_margin NaN, YoY still ok
        self.assertTrue(pd.isna(ccc["fcf_margin"]))
        self.assertAlmostEqual(ccc["sales_growth_q"], 3.0 / 2.9 - 1)

    def test_unmapped_sector_raises(self):
        bad = [{"TICKER": "ZZZ", "NAME": "Zed",
                "INDUSTRY_GROUP_NAME": "Quantum Services"}]
        _write_zip(self.raw / "companies_bad.zip", bad, "companies.csv")
        uni = pd.DataFrame({"ticker": ["ZZZ"], "index_membership": ["SP500"]})
        with patch.object(universe_live, "read_universe_csv", return_value=uni):
            with self.assertRaises(ValueError):
                universe_live.build_live_universe("dummy.csv", self.raw)


class TestBetaFallback(unittest.TestCase):
    def _price_zip(self, path, rows):
        _write_zip(path, rows, "prices.csv")

    def _series(self, ticker, closes, start="2025-09-01"):
        rows = []
        d = pd.Timestamp(start)
        for c in closes:
            while d.weekday() >= 5:
                d += pd.Timedelta(days=1)
            rows.append({"TICKER": ticker, "DATE": str(d.date()),
                         "CLOSE": c, "ADJ_CLOSE": c,
                         "FIFTY_TWO_WEEK_HIGH": c, "FIFTY_TWO_WEEK_LOW": c})
            d += pd.Timedelta(days=1)
        return rows

    def test_clean_series_gives_beta(self):
        # AAA tracks SPY one-for-one -> beta ~1
        tmp = Path(tempfile.mkdtemp())
        try:
            closes = [100.0 * (1.001 ** i) for i in range(300)]
            rows = self._series("AAA", closes) + self._series("SPY", closes)
            self._price_zip(tmp / "stock_prices_test.zip", rows)
            beta = universe_live._fallback_beta(
                tmp, {"AAA"}, pd.Timestamp("2026-09-28"))
            self.assertAlmostEqual(beta["AAA"], 1.0, places=2)
        finally:
            shutil.rmtree(tmp)

    def test_extreme_jump_quarantined_to_nan(self):
        # 12x overnight jump (ticker contamination pattern) -> NaN, not garbage
        tmp = Path(tempfile.mkdtemp())
        try:
            closes = [100.0] * 150 + [1200.0] + [1200.0] * 149
            rows = self._series("BAD", closes)
            rows += self._series("SPY", [600.0] * 300)
            self._price_zip(tmp / "stock_prices_test.zip", rows)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                beta = universe_live._fallback_beta(
                    tmp, {"BAD"}, pd.Timestamp("2026-09-28"))
            self.assertTrue(pd.isna(beta["BAD"]))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
