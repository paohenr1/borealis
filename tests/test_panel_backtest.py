"""Tests for the panel-backtest engine extensions: explicit rebalance dates
and the delisting fill. The lookahead/cost core is covered by test_backtest.py.
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.backtest.engine import BacktestConfig, run_backtest
from borealis.backtest import panel_backtest as pb


def _panels(n_days=8):
    dates = pd.date_range("2020-01-01", periods=n_days, freq="D")
    cols = ["A", "B", "C", "D", "E"]
    prices = pd.DataFrame(100.0, index=dates, columns=cols)
    prices.loc[dates[2]:, "A"] = 110.0   # A +10% from day 2
    prices.loc[dates[4]:, "B"] = 120.0   # B +20% from day 4
    signals = pd.DataFrame(np.nan, index=dates, columns=cols)
    signals.loc[dates[1]] = [5.0, 4.0, 3.0, 2.0, 1.0]  # signal dated day 1
    signals.loc[dates[5]] = [1.0, 2.0, 3.0, 4.0, 5.0]  # flipped at day 5
    return prices, signals


class TestExplicitRebalanceDates(unittest.TestCase):
    def test_trade_dates_used(self):
        prices, signals = _panels()
        sig = signals.ffill()
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[prices.index[2], prices.index[6]],
                             periods_per_year=12)
        res = run_backtest(prices, sig, cfg)
        # trades at day 2 and day 6; holding periods day2->day6, day6->day7
        self.assertEqual(list(res.quantile_returns.index),
                         [prices.index[2], prices.index[6]])
        # at day 2, lagged signal = day-1 ranking -> A top quintile;
        # A rises 0% over day2->day6 (already at 110)
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], 0.0)

    def test_unknown_date_rejected(self):
        prices, signals = _panels()
        cfg = BacktestConfig(
            rebalance_dates=[pd.Timestamp("1999-01-01")])
        with self.assertRaises(ValueError):
            run_backtest(prices, signals.ffill(), cfg)


class TestDelistFill(unittest.TestCase):
    def test_delisted_member_filled(self):
        prices, signals = _panels()
        # C vanishes after day 3 (delisted); rank C top at day-1 signal
        prices.loc[prices.index[4]:, "C"] = np.nan
        sig = signals.ffill()
        sig.loc[prices.index[1]] = [1.0, 2.0, 5.0, 3.0, 4.0]  # C top
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[prices.index[2]],
                             delist_fill=-1.0)
        res = run_backtest(prices, sig, cfg)
        # Q5 holds only C: entered 100, delisted -> -100%
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], -1.0)

    def test_no_delist_fill_keeps_old_behavior(self):
        prices, signals = _panels()
        prices.loc[prices.index[4]:, "C"] = np.nan
        sig = signals.ffill()
        sig.loc[prices.index[1]] = [1.0, 2.0, 3.0, 4.0, 5.0]
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[prices.index[2]],
                             delist_fill=None)
        res = run_backtest(prices, sig, cfg)
        # NaN hold -> 0 contribution (never-held tickers contribute nothing)
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], 0.0)


class TestWinsorizeHold(unittest.TestCase):
    def test_extreme_return_clipped(self):
        dates = pd.date_range("2020-01-01", periods=4, freq="D")
        cols = [f"S{i}" for i in range(10)]
        prices = pd.DataFrame(100.0, index=dates, columns=cols)
        prices.loc[dates[2]:, "S0"] = 100.0 * 101  # +10000% data error
        signals = pd.DataFrame(np.nan, index=dates, columns=cols)
        signals.loc[dates[0]] = np.arange(10.0)  # S0 bottom quintile
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[dates[1]],
                             winsorize_hold=(0.01, 0.99))
        res = run_backtest(prices, signals.ffill(), cfg)
        # S0's +10000% is clipped to the 99th pct of the cross-section,
        # so no quintile can book the raw error
        self.assertLess(res.quantile_returns["Q1"].iloc[0], 50.0)

    def test_none_disables(self):
        dates = pd.date_range("2020-01-01", periods=4, freq="D")
        cols = [f"S{i}" for i in range(10)]
        prices = pd.DataFrame(100.0, index=dates, columns=cols)
        prices.loc[dates[2]:, "S0"] = 200.0
        signals = pd.DataFrame(np.nan, index=dates, columns=cols)
        signals.loc[dates[0]] = np.arange(10.0)
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[dates[1]],
                             winsorize_hold=None)
        res = run_backtest(prices, signals.ffill(), cfg)
        self.assertAlmostEqual(res.quantile_returns["Q1"].iloc[0], 0.5)


class TestExitFill(unittest.TestCase):
    def _gap_panels(self):
        dates = pd.date_range("2020-01-01", periods=6, freq="D")
        cols = ["A", "B", "C", "D", "E"]
        prices = pd.DataFrame(100.0, index=dates, columns=cols)
        # C: gap (missing day 3-4, back day 5); D: permanently gone at day 3
        prices.loc[dates[3]:dates[4], "C"] = np.nan
        prices.loc[dates[3]:, "D"] = np.nan
        signals = pd.DataFrame(np.nan, index=dates, columns=cols)
        signals.loc[dates[0]] = [1.0, 2.0, 5.0, 4.0, 3.0]  # C top, D 2nd
        return prices, signals

    def test_gap_books_zero_permanent_books_fill(self):
        prices, signals = self._gap_panels()
        idx = prices.index
        exit_fill = pd.DataFrame(np.nan, index=idx, columns=prices.columns)
        # first period exits at idx[3]: C gappy, D permanently gone
        exit_fill.loc[idx[3], "C"] = 0.0    # gap
        exit_fill.loc[idx[3], "D"] = -0.3   # permanent
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[idx[1], idx[3]],
                             delist_fill=-1.0, exit_fill=exit_fill)
        res = run_backtest(prices, signals.ffill(), cfg)
        # Q5 holds only C (gap -> 0.0); Q4 holds only D (-0.3)
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], 0.0)
        self.assertAlmostEqual(res.quantile_returns["Q4"].iloc[0], -0.3)

    def test_exit_fill_falls_back_to_delist_fill(self):
        prices, signals = self._gap_panels()
        idx = prices.index
        cfg = BacktestConfig(n_quantiles=5, signal_lag=1, cost_bps=0.0,
                             rebalance_dates=[idx[1], idx[3]],
                             delist_fill=-1.0, exit_fill=None)
        res = run_backtest(prices, signals.ffill(), cfg)
        self.assertAlmostEqual(res.quantile_returns["Q5"].iloc[0], -1.0)


class TestSpreadCostAccounting(unittest.TestCase):
    def test_both_legs_pay(self):
        dates = pd.date_range("2020-01-01", periods=4, freq="D")
        cols = [f"S{i}" for i in range(10)]
        prices = pd.DataFrame(100.0, index=dates, columns=cols)
        prices.loc[dates[2]:, "S9"] = 110.0  # top quintile +10%
        prices.loc[dates[2]:, "S0"] = 90.0   # bottom quintile -10%
        signals = pd.DataFrame(np.nan, index=dates, columns=cols)
        signals.loc[dates[0]] = np.arange(10.0)
        sig = signals.ffill()
        gross = run_backtest(prices, sig,
                             BacktestConfig(n_quantiles=5, signal_lag=1,
                                            cost_bps=0.0,
                                            rebalance_dates=[dates[1]]))
        net = run_backtest(prices, sig,
                           BacktestConfig(n_quantiles=5, signal_lag=1,
                                          cost_bps=100.0,  # 1% one-way
                                          rebalance_dates=[dates[1]]))
        summ = pb.summarize_spread(gross, net, 100.0)
        # gross spread = 0.05 - (-0.05) = 0.10; each leg turns over 0.5
        # (from flat, 0.5*|w|_1) -> cost 2 * 0.5 * 1% = 0.01; net = 0.09
        self.assertAlmostEqual(summ["ann_return"], 0.09 * 12, places=6)


class TestTradeCalendar(unittest.TestCase):
    def test_month_end_plus_one(self):
        dates = pd.DatetimeIndex([pd.Timestamp("2020-01-30"),
                                  pd.Timestamp("2020-01-31"),
                                  pd.Timestamp("2020-02-03"),
                                  pd.Timestamp("2020-02-28"),
                                  pd.Timestamp("2020-03-02"),
                                  pd.Timestamp("2020-03-31"),
                                  pd.Timestamp("2020-04-01")])
        me = [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-28"),
              pd.Timestamp("2020-03-31")]
        trades = pb.trade_calendar(list(dates), me)
        # 2020-03-31 + 1 has no following trade date -> dropped
        self.assertEqual(list(trades),
                         [pd.Timestamp("2020-02-03"),
                          pd.Timestamp("2020-03-02")])


class TestBuildSignalFrameProxies(unittest.TestCase):
    def test_default_factors_cover_every_proxy_factor(self):
        # Regression: build_signal_frame once hardcoded
        # ("mom_12m1m", "vol_126d") as its proxy list, so when beta_252d
        # joined PROXY_FACTORS the lowvol sleeve silently came out empty.
        # Every sleeve built on a proxy factor must come out non-empty.
        import tempfile
        rng = np.random.default_rng(0)
        n = 260
        dates = pd.bdate_range("2020-01-01", periods=n)
        spy_rets = rng.normal(0.0005, 0.01, n)
        aaa_rets = 1.5 * spy_rets + rng.normal(0, 0.005, n)
        px = {"SPY": 100 * np.cumprod(1 + spy_rets),
              "AAA": 100 * np.cumprod(1 + aaa_rets)}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            prow = []
            for t, arr in px.items():
                for d, p in zip(dates, arr):
                    prow.append({"ticker": t, "date": d, "adj_close": p})
            pd.DataFrame(prow).to_parquet(td / "prices.parquet")
            panel_dir = td / "panel" / "year=2020"
            panel_dir.mkdir(parents=True)
            frow = []
            for t in px:
                for d in dates:
                    frow.append({"ticker": t, "date": d, "sector": "Tech",
                                 "roe": 0.10})
            pd.DataFrame(frow).to_parquet(panel_dir / "part.parquet")
            sig = pb.build_signal_frame(td / "panel", td / "prices.parquet",
                                        [dates[-1]])
        self.assertTrue(sig["sleeve_lowvol"].notna().any(),
                        "sleeve_lowvol empty -- beta_252d was dropped")
        self.assertTrue(sig["sleeve_momentum"].notna().any(),
                        "sleeve_momentum empty -- mom_12m1m was dropped")


class TestLargeCapUniverse(unittest.TestCase):
    def _panel(self, td):
        td = Path(td)
        panel_dir = td / "panel"
        panel_dir.mkdir(parents=True)
        rows = [
            # (date, ticker, enterprise_value, market_cap)
            ("2020-01-31", "BIG", 100.0, 90.0),
            ("2020-01-31", "MID", 50.0, 45.0),
            ("2020-01-31", "SML", 10.0, 9.0),
            ("2020-01-31", "NOEV", None, 60.0),    # mc fallback -> 2nd
            ("2020-01-31", "NEGEV", -5.0, 70.0),    # nonpos EV -> mc -> 1st
            ("2020-01-31", "ETF", None, None),      # excluded entirely
            ("2020-02-29", "BIG", 100.0, 90.0),
            ("2020-02-29", "MID", 50.0, 45.0),
            ("2020-02-29", "SML", 10.0, 9.0),
        ]
        df = pd.DataFrame(
            [{"ticker": t, "date": pd.Timestamp(d),
              "enterprise_value": ev, "market_cap": mc}
             for d, t, ev, mc in rows])
        df.to_parquet(panel_dir / "part.parquet")
        return panel_dir

    def test_top_n_ranking_with_fallbacks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            panel = self._panel(td)
            elig = pb.large_cap_universe(
                panel, [pd.Timestamp("2020-01-31")], top_n=3)
            got = sorted(elig["ticker"].tolist())
            # BIG(100), NEGEV via mc(70), NOEV via mc(60); MID(50) cut
            self.assertEqual(got, ["BIG", "NEGEV", "NOEV"])
            self.assertNotIn("ETF", got)

    def test_per_date_and_date_filter(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            panel = self._panel(td)
            elig = pb.large_cap_universe(
                panel, [pd.Timestamp("2020-01-31"),
                        pd.Timestamp("2020-02-29")], top_n=2)
            by_date = elig.groupby("date")["ticker"].apply(sorted)
            self.assertEqual(by_date[pd.Timestamp("2020-01-31")],
                             ["BIG", "NEGEV"])
            self.assertEqual(by_date[pd.Timestamp("2020-02-29")],
                             ["BIG", "MID"])
            # only requested dates appear
            self.assertEqual(set(elig["date"].unique()),
                             {pd.Timestamp("2020-01-31"),
                              pd.Timestamp("2020-02-29")})

    def test_pre_filter_zscores_within_universe(self):
        # pre_filter_top_n restricts the frame BEFORE z-scoring: only
        # eligible tickers appear, and z-scores are relative to them.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            dates = pd.bdate_range("2020-01-01", periods=300)
            panel_dir = td / "panel"
            panel_dir.mkdir(parents=True)
            tickers = ["BIG", "MID", "SML", "TINY"]
            evs = {"BIG": 100.0, "MID": 50.0, "SML": 10.0, "TINY": 1.0}
            roes = {"BIG": 0.30, "MID": 0.20, "SML": 0.10, "TINY": 0.01}
            frow = []
            for t in tickers:
                for d in dates:
                    frow.append({"ticker": t, "date": d, "sector": "Tech",
                                 "roe": roes[t],
                                 "enterprise_value": evs[t],
                                 "market_cap": evs[t]})
            pd.DataFrame(frow).to_parquet(panel_dir / "part.parquet")
            prow = []
            for t in tickers:
                for d in dates:
                    prow.append({"ticker": t, "date": d,
                                 "adj_close": 100.0 + hash(t) % 10})
            pd.DataFrame(prow).to_parquet(td / "prices.parquet")
            sig = pb.build_signal_frame(
                panel_dir, td / "prices.parquet", [dates[-1]],
                factors=["roe"], pre_filter_top_n=2)
            got = sorted(sig["ticker"].unique().tolist())
            self.assertEqual(got, ["BIG", "MID"])
            # z-scored within the 2-ticker universe: BIG above mean
            z = sig.set_index("ticker")["sleeve_quality"]
            self.assertGreater(float(z["BIG"]), float(z["MID"]))


class TestLongOnlyVsSpy(unittest.TestCase):
    def _spy_panel(self, td):
        panel = Path(td) / "panel"
        panel.mkdir()
        rows = [{"ticker": "SPY", "date": pd.Timestamp(d), "adj_close": px}
                for d, px in [("2020-01-31", 400.0), ("2020-02-29", 404.0),
                              ("2020-03-31", 400.0), ("2020-04-30", 408.0)]]
        pd.DataFrame(rows).to_parquet(panel / "part.parquet")
        return panel

    def test_spy_benchmark_monthly_returns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            panel = self._spy_panel(td)
            trades = pd.DatetimeIndex([pd.Timestamp(d) for d in
                                       ["2020-01-31", "2020-02-29",
                                        "2020-03-31", "2020-04-30"]])
            spy = pb.spy_benchmark(panel, trades)
            self.assertEqual(list(spy.index), list(trades[:-1]))
            self.assertAlmostEqual(spy.iloc[0], 0.01)
            self.assertAlmostEqual(spy.iloc[1], 400.0 / 404.0 - 1.0)
            self.assertAlmostEqual(spy.iloc[2], 0.02)

    def test_spy_benchmark_missing_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            panel = Path(td) / "panel"
            panel.mkdir()
            pd.DataFrame([{"ticker": "QQQ",
                           "date": pd.Timestamp("2020-01-31"),
                           "adj_close": 100.0}]
                         ).to_parquet(panel / "part.parquet")
            trades = pd.DatetimeIndex([pd.Timestamp("2020-01-31"),
                                       pd.Timestamp("2020-02-29")])
            with self.assertRaises(ValueError):
                pb.spy_benchmark(panel, trades)

    def test_summarize_longonly_stats(self):
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d in
                                   ["2020-01-31", "2020-02-29",
                                    "2020-03-31", "2020-04-30"]])
        q5 = pd.Series([0.02, -0.01, 0.03, 0.01], index=idx)
        turn = pd.Series([0.4, 0.5, 0.3, 0.4], index=idx)
        spy = pd.Series([0.01, -0.02, 0.01, 0.005], index=idx)
        s = pb.summarize_longonly(q5, turn, spy)
        self.assertEqual(s["periods"], 4)
        self.assertAlmostEqual(s["ann_return"], q5.mean() * 12)
        self.assertAlmostEqual(s["ann_active_return"],
                               (q5 - spy).mean() * 12)
        self.assertAlmostEqual(s["avg_turnover_oneway"], turn.mean())
        self.assertAlmostEqual(s["spy_ann_return"], spy.mean() * 12)
        self.assertLess(s["max_drawdown"], 0)
        self.assertEqual(s["max_dd_peak"][:10], "2020-01-31")
        self.assertEqual(s["max_dd_trough"][:10], "2020-02-29")
        self.assertEqual(s["max_dd_recovered"][:10], "2020-03-31")
        self.assertGreater(s["information_ratio"], 0)
        self.assertAlmostEqual(s["hit_rate"], 0.75)

    def test_summarize_longonly_aligns_indexes(self):
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d in
                                   ["2020-01-31", "2020-02-29",
                                    "2020-03-31", "2020-04-30"]])
        q5 = pd.Series([0.02, -0.01, 0.03, 0.01], index=idx)
        turn = pd.Series([0.4, 0.5, 0.3, 0.4], index=idx)
        spy = pd.Series([0.01, -0.02, 0.01], index=idx[:-1])
        s = pb.summarize_longonly(q5, turn, spy)
        self.assertEqual(s["periods"], 3)

    def test_ew_benchmark_delist_economics(self):
        # C permanently delists -> -0.3; D gaps one period -> 0.0.
        # Booking -1.0 on every gap (old behavior) would phantom-bankrupt
        # the benchmark on gappy microcaps.
        dates = pd.DatetimeIndex([pd.Timestamp(d) for d in
                                  ["2020-01-31", "2020-02-29",
                                   "2020-03-31"]])
        prices = pd.DataFrame({
            "A": [100.0, 110.0, 121.0],
            "B": [100.0, 100.0, 100.0],
            "C": [100.0, np.nan, np.nan],
            "D": [100.0, np.nan, 105.0],
        }, index=dates)
        uni = pd.DataFrame({
            "date": [dates[0]] * 4 + [dates[1]] * 4,
            "ticker": ["A", "B", "C", "D"] * 2,
            "z_composite": [1.0] * 8,
        })
        ef = pb.build_exit_fill(prices, dates)
        bench = pb.equal_weight_benchmark(prices, dates, uni, ef)
        # period 1: (0.10 + 0.00 - 0.30 + 0.00)/4
        # period 2: C and D have no entry price -> 0.0, like the engine's
        # never-held tickers: (0.10 + 0.00 + 0.00 + 0.00)/4
        self.assertAlmostEqual(bench.iloc[0], -0.05)
        self.assertAlmostEqual(bench.iloc[1], 0.025)


if __name__ == "__main__":
    unittest.main()
