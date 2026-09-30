#!/usr/bin/env python3
"""Borealis first real backtest on the Intrinio PIT panel.

Example:
    PYTHONPATH=src python3 scripts/backtest_panel.py \
        --panel data/processed/intrinio/panel \
        --prices data/processed/intrinio/prices_clean.parquet \
        --out data/processed/backtest_first_2026-09-28

Read-only on the panel and price file. Writes quintile returns, turnover,
stats, spread series and a run config JSON under --out.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.backtest import panel_backtest as pb  # noqa: E402


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def main() -> None:
    ap = argparse.ArgumentParser(prog="backtest_panel")
    ap.add_argument("--panel", default="data/processed/intrinio/panel")
    ap.add_argument("--prices",
                    default="data/processed/intrinio/prices_clean.parquet")
    ap.add_argument("--out", default="data/processed/backtest_first_2026-09-28")
    ap.add_argument("--max-dates", type=int, default=None,
                    help="use only the last N month-ends (smoke runs)")
    ap.add_argument("--costs", type=float, nargs="*", default=[0.0, 10.0],
                    help="one-way cost levels in bps to run")
    ap.add_argument("--top-n", type=int, default=None,
                    help="large-cap-only run: at each month-end keep only the "
                         "top N tickers by enterprise_value (market_cap "
                         "fallback). Signals are computed on the full panel "
                         "first (identical methodology), then rows outside "
                         "the top-N are dropped.")
    ap.add_argument("--pre-filter", action="store_true",
                    help="with --top-n, apply the universe filter BEFORE "
                         "z-scoring (sector-neutral z within the large-cap "
                         "universe, as the live model does within its 518).")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    all_dates = pb.panel_trading_dates(args.panel)
    month_ends = pb.month_end_dates(all_dates)
    if args.max_dates:
        month_ends = month_ends[-args.max_dates:]
    print(f"[bt] {len(all_dates)} trading days, "
          f"{len(month_ends)} month-ends "
          f"({month_ends[0].date()} -> {month_ends[-1].date()})", flush=True)

    print("[bt] building signal frame ...", flush=True)
    sig = pb.build_signal_frame(args.panel, args.prices, month_ends,
                                pre_filter_top_n=(args.top_n
                                                  if args.pre_filter
                                                  else None))
    if args.top_n and not args.pre_filter:
        elig = pb.large_cap_universe(args.panel, month_ends, args.top_n)
        n_before = len(sig)
        sig = sig.merge(elig, on=["date", "ticker"], how="inner")
        print(f"[bt] large-cap filter: {len(sig):,}/{n_before:,} rows kept "
              f"(top {args.top_n}/date by EV)", flush=True)
    elif args.top_n:
        print(f"[bt] large-cap pre-filter: top {args.top_n}/date by EV, "
              f"z-scored within universe", flush=True)
    n_sig = int(sig["z_composite"].notna().sum())
    tickers = sorted(sig.loc[sig["z_composite"].notna(), "ticker"].unique())
    print(f"[bt] signal frame: {len(sig):,} rows, {n_sig:,} valid z, "
          f"{len(tickers):,} tickers", flush=True)

    print("[bt] building price matrix ...", flush=True)
    prices = pb.build_price_matrix(args.panel, tickers)
    # The filtered ticker set may not cover every panel date (e.g. the
    # 2021-01-01 holiday); reindex to the full calendar so trade dates
    # always resolve (same treatment as the broad run).
    prices = prices.reindex(all_dates)
    print(f"[bt] prices: {prices.shape[0]} days x {prices.shape[1]} tickers",
          flush=True)

    trade_dates = pb.trade_calendar(all_dates, month_ends)
    print(f"[bt] {len(trade_dates)} trade dates "
          f"({trade_dates[0].date()} -> {trade_dates[-1].date()})", flush=True)
    sig_mat = pb.signal_matrix(sig, prices.index)

    # --- delisting incidence (held at t0, no price at t1) ---
    um = sig.pivot_table(index="date", columns="ticker", values="z_composite",
                         aggfunc="last").notna()
    n_held = n_delist = 0
    for k in range(len(trade_dates) - 1):
        t0, t1 = trade_dates[k], trade_dates[k + 1]
        m = um.index[um.index <= t0].max()
        members = [c for c in um.columns[um.loc[m]] if c in prices.columns]
        e0 = prices.loc[t0, members]
        ok = e0.notna()
        n_held += int(ok.sum())
        n_delist += int((ok & prices.loc[t1, members].isna()).sum())
    print(f"[bt] delisting incidence: {n_delist:,}/{n_held:,} held positions "
          f"({n_delist / max(n_held, 1):.3%})", flush=True)

    results: dict = {"delist_incidence": n_delist / max(n_held, 1),
                     "n_trade_dates": len(trade_dates),
                     "n_tickers": len(tickers)}

    # --- main spec: full universe (permanent delists at -30%) ---
    runs = pb.run_configs(prices, sig_mat, trade_dates,
                          tuple(args.costs))
    res_gross = runs[0.0]
    for cost, res in runs.items():
        tag = f"full_{cost:g}bps"
        res.quantile_returns.to_csv(out / f"quantile_returns_{tag}.csv")
        res.turnover.to_csv(out / f"turnover_{tag}.csv")
        res.stats.to_csv(out / f"stats_{tag}.csv")
        summ = pb.summarize_spread(res_gross, res, cost)
        results[tag] = summ
        (res_gross.quantile_returns["Q5"] - res_gross.quantile_returns["Q1"]
         - (res.turnover["Q5"] + res.turnover["Q1"]) * cost / 1e4).to_csv(
            out / f"spread_Q5_Q1_{tag}.csv", header=True)
        print(f"[bt] {tag}: spread ann_ret={summ['ann_return']:+.2%} "
              f"sharpe={summ['sharpe']:+.2f} maxDD={summ['max_drawdown']:.2%} "
              f"turnover={summ['avg_turnover_ls']:.2f}", flush=True)

    # --- sensitivity: permanent delists at -100% (conservative bound) ---
    runs_dl = pb.run_configs(prices, sig_mat, trade_dates, (0.0, 10.0),
                             perm_delist_fill=-1.0)
    summ_dl = pb.summarize_spread(runs_dl[0.0], runs_dl[10.0], 10.0)
    results["full_10bps_delist100"] = summ_dl
    print(f"[bt] full_10bps_delist100: spread ann_ret={summ_dl['ann_return']:+.2%} "
          f"sharpe={summ_dl['sharpe']:+.2f} maxDD={summ_dl['max_drawdown']:.2%}",
          flush=True)

    # --- sensitivity: min $5 price at signal date ---
    sig_px = sig.merge(
        prices.stack().rename("px_at_signal").reset_index(),
        on=["ticker", "date"], how="left")
    sig_px.loc[(sig_px["px_at_signal"] < pb.MIN_PX_SENSITIVITY)
               | sig_px["px_at_signal"].isna(), "z_composite"] = np.nan
    sig_mat_px = pb.signal_matrix(sig_px, prices.index)
    # tickers filtered out on every date vanish from the pivot (NaN values
    # are dropped); restore the full column set so the engine's shape check
    # passes -- they are simply never held (signal always NaN).
    sig_mat_px = sig_mat_px.reindex(columns=prices.columns)
    runs_px = pb.run_configs(prices, sig_mat_px, trade_dates, (0.0, 10.0))
    res_px = runs_px[10.0]
    res_px.quantile_returns.to_csv(out / "quantile_returns_px5_10bps.csv")
    res_px.turnover.to_csv(out / "turnover_px5_10bps.csv")
    res_px.stats.to_csv(out / "stats_px5_10bps.csv")
    (runs_px[0.0].quantile_returns["Q5"] - runs_px[0.0].quantile_returns["Q1"]
     - (res_px.turnover["Q5"] + res_px.turnover["Q1"]) * 10.0 / 1e4).to_csv(
        out / "spread_Q5_Q1_px5_10bps.csv", header=True)
    summ_px = pb.summarize_spread(runs_px[0.0], res_px, 10.0)
    results["px5_10bps"] = summ_px
    print(f"[bt] px5_10bps: spread ann_ret={summ_px['ann_return']:+.2%} "
          f"sharpe={summ_px['sharpe']:+.2f} maxDD={summ_px['max_drawdown']:.2%}",
          flush=True)

    # --- PRIMARY: long-only Q5 vs SPY (10bps one-way, long side only) ---
    # The L/S spread machinery above is kept as a diagnostic; the
    # long-only leg is the production evaluation. Shorting is cut:
    # the short book was unshortable junk and its modeled costs fiction
    # (drawdown autopsy 2026-09-30).
    res_lo = runs[10.0]
    q5_net = res_lo.quantile_returns["Q5"]
    q5_turn = res_lo.turnover["Q5"]
    spy = pb.spy_benchmark(args.panel, trade_dates)
    q5_net.to_csv(out / "longonly_Q5_net_10bps.csv", header=True)
    (q5_net - spy).dropna().to_csv(out / "longonly_Q5_active_vs_spy_10bps.csv",
                                   header=True)
    lo = pb.summarize_longonly(q5_net, q5_turn, spy)
    results["longonly_Q5_vs_spy_10bps"] = lo
    print(f"[bt] LONG-ONLY Q5 vs SPY: ann_ret={lo['ann_return']:+.2%} "
          f"active={lo['ann_active_return']:+.2%} "
          f"IR={lo['information_ratio']:+.2f} "
          f"maxDD={lo['max_drawdown']:.2%} "
          f"(peak {lo['max_dd_peak'][:10] if lo['max_dd_peak'] else 'n/a'} -> "
          f"trough {lo['max_dd_trough'][:10] if lo['max_dd_trough'] else 'n/a'}) "
          f"turnover={lo['avg_turnover_oneway']:.2f}", flush=True)

    # --- secondary diagnostic: long-only Q5 vs equal-weight universe ---
    # Same delisting economics as the engine (gaps 0.0, permanent -0.3);
    # without it the benchmark phantom-bankrupts on gappy microcaps.
    exit_fill = pb.build_exit_fill(prices, trade_dates)
    bench = pb.equal_weight_benchmark(prices, trade_dates, sig, exit_fill)
    bench.to_csv(out / "benchmark_ew.csv", header=True)
    active_ew = (q5_net - bench).dropna()
    n_ew = len(active_ew)
    a_ret_ew = float(active_ew.mean() * 12)
    a_vol_ew = float(active_ew.std() * np.sqrt(12)) if n_ew > 1 else 0.0
    results["longonly_Q5_vs_bench_10bps"] = {
        "ann_active_return": a_ret_ew,
        "ann_tracking_error": a_vol_ew,
        "information_ratio": a_ret_ew / a_vol_ew if a_vol_ew else 0.0,
        "bench_ann_return": float(bench.mean() * 12),
        "q5_ann_return": float(q5_net.mean() * 12),
    }
    print(f"[bt] long-only Q5 vs EW universe: {a_ret_ew:+.2%} ann., "
          f"IR={a_ret_ew / a_vol_ew:+.2f}" if a_vol_ew else "", flush=True)

    # --- composite rank IC (cheap, from signal frame + panel fwd returns) ---
    results["composite_ic_21d"] = pb.composite_ic(sig, args.panel)
    ic = results["composite_ic_21d"]
    print(f"[bt] composite IC21: {ic['mean']:+.4f} (t={ic['tstat']:+.2f}, "
          f"n={ic['n']})", flush=True)

    results["config"] = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel": str(args.panel),
        "signal": "z_composite: sleeve-weighted sector-neutral z "
                  "(weights from borealis.lab.composite.SLEEVE_WEIGHTS)",
        "universe": ("tickers with non-NaN z_composite at rebalance "
                    "(lab universe)" +
                    (f"; large-cap filter: top {args.top_n}/date by "
                     f"enterprise_value (market_cap fallback)" +
                     (", z-scored within the large-cap universe"
                      if args.pre_filter
                      else ", signals computed on full panel first")
                     if args.top_n else "")),
        "rebalance": "monthly; trade at month-end + 1 trading day "
                     "(t+1 execution)",
        "costs_bps_one_way": list(args.costs),
        "delist_treatment": "missing exit price: 0.0 if ticker trades again "
                            "later (data gap / ticker change, ~76% of cases), "
                            "-0.3 if permanently delisted (Shumway 1997); "
                            "full_10bps_delist100 reruns with -1.0 as the "
                            "conservative bound",
        "holding_return_winsorization": "per-period cross-sectional 1/99 "
                                        "(corrupt adjusted-price defense; "
                                        "e.g. CDT 2023-11 adj_close 1.1e8)",
        "spread_cost_accounting": "dollar-neutral L/S pays one-way costs on "
                                  "BOTH legs: net spread = gross(Q5-Q1) - "
                                  "(turnover_Q5+turnover_Q1)*cost",
        "prices": "adj_close (split+dividend adjusted, total return)",
    }
    (out / "run_summary.json").write_text(
        json.dumps(results, default=_jsonable, indent=1))
    print(f"[bt] wrote {out}", flush=True)


if __name__ == "__main__":
    main()
