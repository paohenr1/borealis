"""Tests for the Intrinio bulk loader and PIT panel (synthetic zips)."""
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.ingest import intrinio_bulk, panel

PRICE_COLS = intrinio_bulk.PRICE_USECOLS


def _price_row(ticker, date, close, adj_close, sec="sec_1", co="com_1",
               **kw):
    row = {
        "SECURITY_ID": sec, "COMPANY_ID": co, "TICKER": ticker,
        "COMP_TICKER": f"{ticker}:US", "EXCH_TICKER": f"{ticker}:UN",
        "DATE": date, "OPEN": close, "HIGH": close, "LOW": close,
        "CLOSE": close, "VOLUME": 1000, "ADJ_OPEN": adj_close,
        "ADJ_HIGH": adj_close, "ADJ_LOW": adj_close, "ADJ_CLOSE": adj_close,
        "ADJ_VOLUME": 1000, "ADJ_FACTOR": 1.0, "EX_DIVIDEND": 0.0,
        "SPLIT_RATIO": 1.0, "FIFTY_TWO_WEEK_HIGH": close,
        "FIFTY_TWO_WEEK_LOW": close,
    }
    row.update(kw)
    return row


def _write_price_zip(path: Path, rows: list[dict], fname: str):
    df = pd.DataFrame(rows, columns=PRICE_COLS)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(fname, df.to_csv(index=False))


def _write_calc_zip(path: Path, rows: list[dict]):
    cols = intrinio_bulk.CALC_WANT
    df = pd.DataFrame(rows, columns=cols)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("X_CALCULATIONS.csv", df.to_csv(index=False))


class TestPriceLoader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)
        rows = [
            _price_row("AAA", "2024-01-02", 10.0, 10.0),
            _price_row("AAA", "2024-01-03", 11.0, 11.0),
            _price_row("AAA", "2024-01-04", 12.0, 12.0),
            _price_row("BBB", "2024-01-02", 20.0, 20.0, sec="sec_2", co="com_2"),
            # bad date -> quarantine
            _price_row("CCC", "not-a-date", 5.0, 5.0, sec="sec_3", co="com_3"),
            # bad adj_close -> quarantine
            _price_row("DDD", "2024-01-02", 5.0, 0.0, sec="sec_4", co="com_4"),
            # missing ticker -> quarantine
            _price_row("", "2024-01-02", 5.0, 5.0, sec="sec_5", co="com_5"),
        ]
        # duplicate (ticker, date): sec_1 (3 rows) beats sec_9 (1 row)
        rows.append(_price_row("AAA", "2024-01-03", 11.0, 99.0, sec="sec_9"))
        _write_price_zip(self.raw / "stock_prices_uscomp_since_2020-01-24_file-1.zip",
                         rows, "stock_prices_uscomp_since_2020-01-24_file-1.csv")
        self.out = self.raw / "prices_clean.parquet"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_dedup_and_quarantine(self):
        rep = intrinio_bulk.load_prices(self.raw, self.out, self.raw / "_q")
        self.assertEqual(rep["rows_in"], 8)
        self.assertEqual(rep["rows_out"], 4)  # 8 - 3 quarantined - 1 dupe
        self.assertEqual(rep["dupes_dropped"], 1)
        self.assertEqual(rep["quarantined"].get("bad_date"), 1)
        self.assertEqual(rep["quarantined"].get("bad_adj_close"), 1)
        self.assertEqual(rep["quarantined"].get("missing_ticker"), 1)

        df = pd.read_parquet(self.out)
        aaa = df[df["ticker"] == "AAA"].sort_values("date")
        # dupe kept the longest-security row (adj_close 11.0, not 99.0)
        self.assertEqual(aaa.loc[aaa["date"] == "2024-01-03", "adj_close"].iloc[0], 11.0)
        self.assertNotIn("CCC", set(df["ticker"]))
        self.assertNotIn("DDD", set(df["ticker"]))
        self.assertTrue((df["adj_close"] > 0).all())

    def test_missing_column_raises(self):
        bad = pd.DataFrame([{"TICKER": "X", "DATE": "2024-01-01"}])
        with zipfile.ZipFile(
                self.raw / "stock_prices_uscomp_since_2020-01-24_file-2.zip",
                "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("x.csv", bad.to_csv(index=False))
        with self.assertRaises(ValueError):
            intrinio_bulk.load_prices(self.raw, self.raw / "o2.parquet")


class TestCalcLoader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _row(self, **kw):
        base = {c: "" for c in intrinio_bulk.CALC_WANT}
        base.update({
            "fundamental_id": "fun_1", "company_id": "com_1", "ticker": "AAA",
            "end_date": "2024-12-31", "fiscal_year": "2024",
            "fiscal_period": "FY", "filing_date": "2025-02-01",
            "first_calculable_at": "2025-02-03", "months": "12",
            "pricetoearnings": "15.0", "marketcap": "1000",
        })
        base.update(kw)
        return base

    def test_ttm_filter_and_pit_date(self):
        rows = [
            self._row(),                                            # FY, both dates -> 2025-02-03
            self._row(fundamental_id="fun_2", fiscal_period="Q1",
                      filing_date="2024-05-01"),                    # quarterly -> skipped
            self._row(fundamental_id="fun_3", fiscal_period="Q1TTM",
                      filing_date="", first_calculable_at=""),      # no dates -> quarantined
        ]
        _write_calc_zip(self.raw / "US_INDU_CALCULATIONS.zip", rows)
        rep = intrinio_bulk.load_calculations(self.raw, self.raw / "c.parquet",
                                              self.raw / "_q")
        self.assertEqual(rep["rows_in"], 3)
        self.assertEqual(rep["rows_out"], 1)
        self.assertEqual(rep["quarantined"].get("no_availability_date"), 1)
        df = pd.read_parquet(self.raw / "c.parquet")
        self.assertEqual(str(df["available_date"].iloc[0])[:10], "2025-02-03")
        self.assertEqual(float(df["pricetoearnings"].iloc[0]), 15.0)


class TestPanel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        # 30 trading days of prices for two tickers
        dates = pd.date_range("2024-01-02", periods=30, freq="B")
        px = []
        for t, base in [("AAA", 100.0), ("BBB", 50.0)]:
            for i, d in enumerate(dates):
                px.append(_price_row(t, d.strftime("%Y-%m-%d"),
                                     base + i, base + i,
                                     sec=f"sec_{t}", co=f"com_{t}"))
        raw = self.d / "raw"
        raw.mkdir()
        _write_price_zip(raw / "stock_prices_uscomp_since_2020-01-24_file-1.zip",
                         px, "p.csv")
        intrinio_bulk.load_prices(raw, self.d / "prices.parquet")
        # fundamentals: vintage available 2024-01-10 (pe=10), then 2024-02-01 (pe=20)
        cols = intrinio_bulk.CALC_WANT
        fu = pd.DataFrame([
            {**{c: "" for c in cols}, **{"company_id": "com_AAA", "ticker": "AAA",
                "end_date": "2023-12-31", "fiscal_year": "2023",
                "fiscal_period": "FY", "filing_date": "2024-01-10",
                "first_calculable_at": "", "pricetoearnings": "10.0"}},
            {**{c: "" for c in cols}, **{"company_id": "com_AAA", "ticker": "AAA",
                "end_date": "2024-03-31", "fiscal_year": "2024",
                "fiscal_period": "Q1TTM", "filing_date": "",
                "first_calculable_at": "2024-02-01", "pricetoearnings": "20.0"}},
        ])
        fu = intrinio_bulk._calc_available(fu)
        fu.to_parquet(self.d / "calcs.parquet", index=False)
        self.companies = pd.DataFrame({
            "company_id": ["com_AAA", "com_BBB"],
            "sector": ["technology", "energy"],
        })
        self.panel_rep = panel.build_panel(self.d / "prices.parquet",
                                           self.d / "calcs.parquet",
                                           self.companies, self.d / "panel",
                                           ticker_batch=10)

    def tearDown(self):
        self.tmp.cleanup()

    def _panel(self):
        return pd.read_parquet(self.d / "panel")

    def test_pit_no_lookahead(self):
        rep = self.panel_rep
        self.assertEqual(rep["tickers"], 2)
        p = self._panel()
        aaa = p[p["ticker"] == "AAA"].sort_values("date")
        # before 2024-01-10: no fundamentals -> pe NaN
        self.assertTrue(aaa.loc[aaa["date"] < "2024-01-10", "pe"].isna().all())
        # 2024-01-10..2024-01-31: pe == 10 (NOT 20: the Feb vintage is future)
        mid = aaa[(aaa["date"] >= "2024-01-10") & (aaa["date"] < "2024-02-01")]
        self.assertTrue((mid["pe"] == 10.0).all())
        late = aaa[aaa["date"] >= "2024-02-01"]
        self.assertTrue((late["pe"] == 20.0).all())
        # sector join + unknown fallback
        self.assertEqual(aaa["sector"].iloc[0], "technology")
        bbb = p[p["ticker"] == "BBB"]
        self.assertEqual(bbb["sector"].iloc[0], "energy")

    def test_forward_returns_need_future_prices(self):
        p = self._panel()
        aaa = p[p["ticker"] == "AAA"].sort_values("date").reset_index(drop=True)
        # price rises 1.0/day from 100: 21d forward return on day 0 = 21/100
        self.assertAlmostEqual(aaa.loc[0, "ret_fwd_21d"], 21 / 100.0, places=6)
        # last 21 rows have no forward window -> NaN (never invented)
        self.assertTrue(aaa["ret_fwd_21d"].iloc[-21:].isna().all())
        # trailing 21d return on day 21 = 21/100
        self.assertAlmostEqual(aaa.loc[21, "ret_21d"], 21 / 100.0, places=6)

    def test_batch_without_fundamentals_keeps_schema(self):
        # calcs for an unrelated ticker -> AAA/BBB batch hits the empty path;
        # output must still carry the renamed factor columns (as NaN)
        cols = intrinio_bulk.CALC_WANT
        fu = pd.DataFrame([
            {**{c: "" for c in cols}, **{"company_id": "com_ZZZ", "ticker": "ZZZ",
                "end_date": "2023-12-31", "fiscal_year": "2023",
                "fiscal_period": "FY", "filing_date": "2024-01-10",
                "first_calculable_at": "", "pricetoearnings": "10.0"}},
        ])
        fu = intrinio_bulk._calc_available(fu)
        fu.to_parquet(self.d / "calcs_zzz.parquet", index=False)
        panel.build_panel(self.d / "prices.parquet", self.d / "calcs_zzz.parquet",
                          self.companies, self.d / "panel_zzz", ticker_batch=10)
        p = pd.read_parquet(self.d / "panel_zzz")
        self.assertIn("pe", p.columns)
        self.assertIn("fund_available_date", p.columns)
        self.assertTrue(p["pe"].isna().all())
        self.assertTrue(p["fund_available_date"].isna().all())

    def test_split_adjusted_returns_have_no_jump(self):
        # 2:1 split: raw close halves, adj_close continuous -> no fake -50% day
        dates = pd.date_range("2024-03-01", periods=10, freq="B")
        rows = []
        for i, d in enumerate(dates):
            raw = 200.0 if i < 5 else 100.0
            rows.append(_price_row("SPL", d.strftime("%Y-%m-%d"), raw,
                                   100.0 + i, sec="sec_s", co="com_s",
                                   SPLIT_RATIO=0.5 if i == 5 else 1.0))
        raw = self.d / "raw2"
        raw.mkdir()
        _write_price_zip(raw / "stock_prices_uscomp_since_2020-01-24_file-1.zip",
                         rows, "p.csv")
        rep = intrinio_bulk.load_prices(raw, self.d / "prices2.parquet")
        df = pd.read_parquet(self.d / "prices2.parquet").sort_values("date")
        rets = df["adj_close"].pct_change().dropna()
        # no single-day crash despite the raw 2:1 split
        self.assertTrue((rets.abs() < 0.05).all())


def _write_income_zip(path: Path, rows: list[dict]):
    cols = intrinio_bulk.INCOME_WANT
    df = pd.DataFrame(rows, columns=cols)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("X_INCOME_STATEMENT.csv", df.to_csv(index=False))


class TestCalcTemplateExtra(unittest.TestCase):
    """grossmargin is INDU-only: kept when present, NaN-filled otherwise."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _row(self, **kw):
        base = {c: "" for c in intrinio_bulk.CALC_WANT}
        base.update({
            "fundamental_id": "fun_1", "company_id": "com_1", "ticker": "AAA",
            "end_date": "2024-12-31", "fiscal_year": "2024",
            "fiscal_period": "FY", "filing_date": "2025-02-01",
            "first_calculable_at": "", "months": "12",
        })
        base.update(kw)
        return base

    def _write_zip(self, path, rows, cols):
        df = pd.DataFrame(rows, columns=cols)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("X_CALCULATIONS.csv", df.to_csv(index=False))

    def test_fin_first_indu_keeps_grossmargin(self):
        fin_cols = [c for c in intrinio_bulk.CALC_WANT if c != "grossmargin"]
        self._write_zip(self.raw / "US_FIN_CALCULATIONS.zip",
                        [self._row(ticker="FINCO")], fin_cols)
        indu_cols = list(intrinio_bulk.CALC_WANT)
        self._write_zip(self.raw / "US_INDU_CALCULATIONS.zip",
                        [self._row(ticker="INDUCO", grossmargin="42.5")],
                        indu_cols)
        rep = intrinio_bulk.load_calculations(self.raw, self.raw / "c.parquet")
        self.assertEqual(rep["rows_out"], 2)
        df = pd.read_parquet(self.raw / "c.parquet")
        self.assertIn("grossmargin", df.columns)
        fin_v = df.loc[df["ticker"] == "FINCO", "grossmargin"].iloc[0]
        indu_v = df.loc[df["ticker"] == "INDUCO", "grossmargin"].iloc[0]
        self.assertTrue(pd.isna(fin_v))
        self.assertAlmostEqual(float(indu_v), 42.5)

    def test_debttoequity_in_both_templates(self):
        self._write_zip(self.raw / "US_FIN_CALCULATIONS.zip",
                        [self._row(ticker="FINCO", debttoequity="1.5")],
                        [c for c in intrinio_bulk.CALC_WANT if c != "grossmargin"])
        rep = intrinio_bulk.load_calculations(self.raw, self.raw / "c.parquet")
        df = pd.read_parquet(self.raw / "c.parquet")
        self.assertIn("debttoequity", df.columns)
        self.assertAlmostEqual(
            float(df.loc[df["ticker"] == "FINCO", "debttoequity"].iloc[0]), 1.5)


class TestIncomeStatements(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _row(self, **kw):
        base = {c: "" for c in intrinio_bulk.INCOME_WANT}
        base.update({
            "fundamental_id": "fun_1", "company_id": "com_1", "ticker": "AAA",
            "end_date": "2024-12-31", "fiscal_year": "2024",
            "fiscal_period": "Q3TTM", "filing_date": "2025-02-01",
            "first_calculable_at": "2025-02-03", "months": "12",
            "totalrevenue": "1000.0",
        })
        base.update(kw)
        return base

    def test_ttm_filter_pit_and_numeric(self):
        rows = [
            self._row(),                                              # kept
            self._row(fundamental_id="fun_2", fiscal_period="Q4",
                      totalrevenue="250.0"),                           # quarterly -> skipped
            self._row(fundamental_id="fun_3", filing_date="",
                      first_calculable_at=""),                         # no dates -> quarantined
        ]
        _write_income_zip(self.raw / "US_INDU_INCOME_STATEMENT.zip", rows)
        _write_income_zip(self.raw / "US_FIN_INCOME_STATEMENT.zip", [])
        rep = intrinio_bulk.load_income_statements(self.raw,
                                                   self.raw / "r.parquet",
                                                   self.raw / "_q")
        self.assertEqual(rep["rows_out"], 1)
        self.assertEqual(rep["quarantined"].get("no_availability_date"), 1)
        df = pd.read_parquet(self.raw / "r.parquet")
        # PIT date = later of filing_date / first_calculable_at
        self.assertEqual(str(df["available_date"].iloc[0])[:10], "2025-02-03")
        self.assertAlmostEqual(float(df["totalrevenue"].iloc[0]), 1000.0)


class TestPanelRevenue(unittest.TestCase):
    """revenue PIT-merge + fcf_margin derivation in build_panel."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        dates = pd.date_range("2024-01-02", periods=30, freq="B")
        px = []
        for t, base in [("AAA", 100.0), ("BBB", 50.0)]:
            for i, d in enumerate(dates):
                px.append(_price_row(t, d.strftime("%Y-%m-%d"),
                                     base + i, base + i,
                                     sec=f"sec_{t}", co=f"com_{t}"))
        raw = self.d / "raw"
        raw.mkdir()
        _write_price_zip(raw / "stock_prices_uscomp_since_2020-01-24_file-1.zip",
                         px, "p.csv")
        intrinio_bulk.load_prices(raw, self.d / "prices.parquet")
        cols = intrinio_bulk.CALC_WANT
        fu = pd.DataFrame([
            {**{c: "" for c in cols}, **{"company_id": "com_AAA", "ticker": "AAA",
                "end_date": "2023-12-31", "fiscal_year": "2023",
                "fiscal_period": "FY", "filing_date": "2024-01-10",
                "first_calculable_at": "", "freecashflow": "500.0"}},
        ])
        fu = intrinio_bulk._calc_available(fu)
        fu.to_parquet(self.d / "calcs.parquet", index=False)
        rv = pd.DataFrame([
            {**{c: "" for c in intrinio_bulk.INCOME_WANT},
             **{"company_id": "com_AAA", "ticker": "AAA",
                "end_date": "2023-12-31", "fiscal_year": "2023",
                "fiscal_period": "FY", "filing_date": "2024-01-15",
                "first_calculable_at": "", "totalrevenue": "2000.0"}},
        ])
        rv = intrinio_bulk._calc_available(rv)
        rv.to_parquet(self.d / "rev.parquet", index=False)
        self.companies = pd.DataFrame({
            "company_id": ["com_AAA", "com_BBB"],
            "sector": ["technology", "energy"],
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_revenue_pit_and_fcf_margin(self):
        panel.build_panel(self.d / "prices.parquet", self.d / "calcs.parquet",
                          self.companies, self.d / "panel", ticker_batch=10,
                          revenue_path=self.d / "rev.parquet")
        p = pd.read_parquet(self.d / "panel")
        self.assertIn("revenue", p.columns)
        self.assertIn("fcf_margin", p.columns)
        aaa = p[p["ticker"] == "AAA"].sort_values("date")
        # revenue vintage available 2024-01-15; before that -> NaN (no lookahead)
        self.assertTrue(aaa.loc[aaa["date"] < "2024-01-15", "revenue"].isna().all())
        late = aaa[aaa["date"] >= "2024-01-15"]
        self.assertTrue((late["revenue"] == 2000.0).all())
        # fcf vintage available 2024-01-10 -> fcf_margin = 500/2000 = 0.25
        # only once BOTH legs are available
        self.assertTrue(aaa.loc[aaa["date"] < "2024-01-15",
                                "fcf_margin"].isna().all())
        self.assertTrue((late["fcf_margin"] == 0.25).all())
        # BBB has no fundamentals -> NaN, never invented
        bbb = p[p["ticker"] == "BBB"]
        self.assertTrue(bbb["revenue"].isna().all())
        self.assertTrue(bbb["fcf_margin"].isna().all())


if __name__ == "__main__":
    unittest.main()
