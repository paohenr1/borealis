"""Loader test against the real Ranks & Earnings workbook (fixture)."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.ingest.loader import load_universe
from borealis.ingest.validate import validate_universe

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "raw" / "ranks_earnings_2026-09-22.xlsx"


class TestLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            raise unittest.SkipTest(
                f"requires licensed workbook (not in git): {FIXTURE.name}")
        cls.df = load_universe(FIXTURE)

    def test_row_count_and_sectors(self):
        self.assertGreater(len(self.df), 300)
        self.assertEqual(self.df["sector"].nunique(), 11)

    def test_expected_columns(self):
        for col in ["ticker", "company", "sector", "pe_ratio", "ps_ratio",
                    "peg_ratio", "sales_growth_q", "trailing_beta"]:
            self.assertIn(col, self.df.columns)

    def test_known_tickers_present(self):
        tickers = set(self.df["ticker"])
        for t in ["WGO", "TSN", "DVN", "NVDA", "TD.TO"]:
            self.assertIn(t, tickers)

    def test_validation_passes(self):
        validate_universe(self.df, "2026-09-22")  # should not raise


if __name__ == "__main__":
    unittest.main()


class TestSuspiciousFlags(unittest.TestCase):
    def _df(self, **overrides):
        base = dict(ticker="TST", company="Test Co", sector="technology",
                    currency="USD", price=100.0, pe_ratio=15.0, ps_ratio=2.0,
                    peg_ratio=1.0, sales_growth_q=0.1, trailing_beta=1.0,
                    pct_above_52w_low=0.5, low_52w=80.0, high_52w=120.0)
        base.update(overrides)
        return pd.DataFrame([base])

    def test_absurd_pe_flagged_not_raised(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate_universe(self._df(pe_ratio=4378.0), "2026-09-22")  # should not raise
        self.assertIn("suspicious", buf.getvalue())
        self.assertIn("TST", buf.getvalue())

    def test_price_outside_52w_range_flagged(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate_universe(self._df(price=10.0), "2026-09-22")
        self.assertIn("outside 52-week range", buf.getvalue())

    def test_clean_row_no_suspicious_section(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate_universe(self._df(), "2026-09-22")
        self.assertNotIn("suspicious", buf.getvalue())


class TestFormatTopN(unittest.TestCase):
    def test_format_top_n_blocks_and_alignment(self):
        from borealis.reporting.tearsheet import format_top_n
        df = pd.DataFrame([
            {"rank": 1, "ticker": "AAA", "company": "AAA Corp", "sector": "technology",
             "composite": 1.23456, "price": 1234.567, "pe_ratio": 16.3689,
             "ps_ratio": 0.6852, "peg_ratio": 1.36},
            {"rank": 2, "ticker": "BBB", "company": "BBB Corp", "sector": "technology",
             "composite": 0.5, "price": 93.22, "pe_ratio": float("nan"),
             "ps_ratio": 0.3714, "peg_ratio": 1.13},
        ])
        out = format_top_n(df, 5)
        self.assertIn("Technology — top 2", out)
        self.assertIn("AAA", out)
        self.assertIn("+1.23", out)      # composite rounded, signed
        self.assertIn("1,234.57", out)   # price thousands separator
        self.assertIn("—", out)          # NaN renders as em dash, not 'nan'


if __name__ == "__main__":
    unittest.main()
