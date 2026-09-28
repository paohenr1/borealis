#!/usr/bin/env python3
"""Borealis factor-efficacy lab: per-sleeve backtests, IC decay, regimes.

Example:
    PYTHONPATH=src python3 scripts/run_factor_lab.py \
        --panel data/processed/intrinio/panel \
        --prices data/processed/intrinio/prices_clean.parquet \
        --out data/processed/factor_lab_2026-09-28

Read-only on the panel and price file. Per sleeve (value, quality,
growth, yield, momentum, lowvol, size) this runs the same costed
quintile engine as the first backtest (t+1 execution, 10 bps one-way on
both legs, gap-vs-permanent delist treatment, 1/99 holding-return
winsorization), plus IC-at-horizon decay, SPY-regime conditioning, and
a sleeve-level rank-correlation matrix.

Universe per sleeve = tickers with a non-NaN sleeve z at rebalance
(each factor tested on its own coverable universe; documented in
borealis.lab.sleeve_backtest).
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
from borealis.lab import (composite as lab_composite,  # noqa: E402
                          corrpca, horizons, ic as lab_ic, regimes,
                          sleeve_backtest as sleeves)


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


COST = 10.0


def main() -> None:
    ap = argparse.ArgumentParser(prog="run_factor_lab")
    ap.add_argument("--panel", default="data/processed/intrinio/panel")
    ap.add_argument("--prices",
                    default="data/processed/intrinio/prices_clean.parquet")
    ap.add_argument("--out", default="data/processed/factor_lab_2026-09-28")
    ap.add_argument("--max-dates", type=int, default=None,
                    help="use only the last N month-ends (smoke runs)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sleeve_names = list(lab_composite.SLEEVES.keys())
    print(f"[lab] sleeves: {sleeve_names}", flush=True)

    all_dates = pb.panel_trading_dates(args.panel)
    month_ends = pb.month_end_dates(all_dates)
    if args.max_dates:
        month_ends = month_ends[-args.max_dates:]
    print(f"[lab] {len(month_ends)} month-ends "
          f"({month_ends[0].date()} -> {month_ends[-1].date()})", flush=True)

    print("[lab] building signal frame ...", flush=True)
    sig = pb.build_signal_frame(args.panel, args.prices, month_ends)
    zcols = [f"sleeve_{s}" for s in sleeve_names]
    tickers = sorted(sig.loc[sig[zcols].notna().any(axis=1),
                             "ticker"].unique())
    print(f"[lab] signal frame: {len(sig):,} rows, "
          f"{len(tickers):,} tickers", flush=True)

    print("[lab] building price matrix ...", flush=True)
    prices = pb.build_price_matrix(args.panel, tickers)
    print(f"[lab] prices: {prices.shape[0]} days x {prices.shape[1]} tickers",
          flush=True)

    trade_dates = pb.trade_calendar(all_dates, month_ends)
    print(f"[lab] {len(trade_dates)} trade dates", flush=True)

    results: dict = {"sleeves": sleeve_names,
                     "n_trade_dates": len(trade_dates),
                     "n_tickers": len(tickers)}

    # ---- 1. per-sleeve costed backtests ----
    print("[lab] running per-sleeve backtests ...", flush=True)
    runs = sleeves.run_sleeve_backtests(prices, sig, trade_dates,
                                        sleeve_names)
    rep = sleeves.sleeve_spread_report(runs, cost=COST)
    rep.to_csv(out / "sleeve_spreads_10bps.csv")
    for s in sleeve_names:
        runs[s][COST].quantile_returns.to_csv(
            out / f"sleeve_quantile_returns_{s}_10bps.csv")
        runs[s][COST].turnover.to_csv(out / f"sleeve_turnover_{s}_10bps.csv")
    for s in sleeve_names:
        r = rep.loc[s]
        print(f"[lab] {s:9s} spread={r['ann_return']:+.2%} "
              f"sharpe={r['sharpe']:+.2f} turn={r['avg_turnover_ls']:.2f} "
              f"short_share={r['short_share']:.0%}", flush=True)
    results["sleeve_spreads"] = rep.reset_index().to_dict("records")

    # ---- 2. IC decay at 1m/3m/6m/12m horizons ----
    print("[lab] forward returns + IC at horizons ...", flush=True)
    fwd = horizons.forward_returns(prices, month_ends)
    ic_h = horizons.ic_at_horizons(sig, fwd, sleeve_names)
    ic_rows, hl_rows = [], []
    for s in sleeve_names:
        means = {}
        for h in horizons.HORIZONS:
            d = ic_h.get(s, {}).get(h, {})
            means[h] = d.get("mean", np.nan)
            ic_rows.append({"sleeve": s, "horizon_d": h,
                            "ic_mean": d.get("mean"), "ic_tstat": d.get("tstat"),
                            "ic_hit": d.get("hit_rate"), "n": d.get("n")})
        hl = horizons.ic_half_life(means)
        hl_rows.append({"sleeve": s, "ic_half_life_d": hl["days"],
                        "censored": hl["censored"], **{
                            f"ic_{h}d": means.get(h) for h in
                            horizons.HORIZONS}})
        ic_str = " ".join(f"IC{h}d={means.get(h, float('nan')):+.4f}"
                          for h in horizons.HORIZONS)
        hl_str = f"HL={hl['days']:.0f}d" if hl["days"] else "HL=n/a"
        print(f"[lab] {s:9s} {ic_str} {hl_str}", flush=True)
    pd.DataFrame(ic_rows).to_csv(out / "ic_horizons.csv", index=False)
    pd.DataFrame(hl_rows).to_csv(out / "ic_half_life.csv", index=False)
    results["ic_horizons"] = ic_rows
    results["ic_half_life"] = hl_rows

    # ---- 3. regime conditioning (SPY up/down, realized-vol high/low) ----
    print("[lab] market regimes ...", flush=True)
    reg = regimes.spy_regimes(prices, month_ends)
    print(f"[lab] up months: {int(reg['mkt_up'].sum())}/{len(reg)}, "
          f"high-vol months: {int(reg['high_vol'].sum())}/{len(reg)}",
          flush=True)
    fwd21 = fwd[fwd["h"] == 21][["date", "ticker", "fwd_ret"]]
    reg_rows, spread_reg_rows = [], []
    # trade date -> signal month-end (trade = month-end + 1 trading day)
    pos = {d: i for i, d in enumerate(all_dates)}
    me_of_trade = {}
    for m in month_ends:
        i = pos.get(m)
        if i is not None and i + 2 < len(all_dates):
            me_of_trade[all_dates[i + 1]] = m
    for s in sleeve_names:
        zc = f"sleeve_{s}"
        m = sig[["date", "ticker", zc]].merge(fwd21, on=["date", "ticker"],
                                             how="inner").dropna()
        ics = lab_ic.ic_series(m, zc, "fwd_ret")
        by_reg = regimes.ic_by_regime(ics, reg)
        row = {"sleeve": s}
        for flag in ("mkt_up", "high_vol"):
            for k, v in by_reg[flag].items():
                if isinstance(v, dict):
                    row[f"{flag}_{k}_ic"] = v["mean"]
                    row[f"{flag}_{k}_t"] = v["tstat"]
                    row[f"{flag}_{k}_n"] = v["n"]
                else:
                    row[f"{flag}_{k}"] = v
        reg_rows.append(row)
        # regime-conditioned net spread from the engine's trade dates
        q = runs[s][COST].quantile_returns
        tnover = runs[s][COST].turnover
        gross = q["Q5"] - q["Q1"]
        net = gross - (tnover["Q5"] + tnover["Q1"]) * COST / 1e4
        srow = {"sleeve": s}
        for flag, labs in (("mkt_up", ("up", "down")),
                           ("high_vol", ("high_vol", "low_vol"))):
            for val, lab in zip((True, False), labs):
                dates = [t for t in net.index
                         if t in me_of_trade
                         and me_of_trade[t] in reg.index
                         and reg.loc[me_of_trade[t], flag] == val]
                sub = net.loc[dates]
                srow[f"{lab}_spread_ann"] = (
                    float(sub.mean() * 12) if len(sub) else np.nan)
                srow[f"{lab}_n"] = len(sub)
        spread_reg_rows.append(srow)
    pd.DataFrame(reg_rows).to_csv(out / "regime_ic.csv", index=False)
    pd.DataFrame(spread_reg_rows).to_csv(out / "regime_spreads.csv",
                                         index=False)
    results["regime_ic"] = reg_rows
    results["regime_spreads"] = spread_reg_rows
    results["regime_counts"] = {
        "up_months": int(reg["mkt_up"].sum()),
        "down_months": int((~reg["mkt_up"]).sum()),
        "high_vol_months": int(reg["high_vol"].sum()),
        "low_vol_months": int((~reg["high_vol"]).sum()),
    }

    # ---- 4. sleeve-level rank correlation + PCA ----
    print("[lab] sleeve rank correlations ...", flush=True)
    corr_frame = sig[["date", "ticker"] + zcols].dropna(
        subset=zcols, how="all")
    mats = corrpca.date_corr_matrices(corr_frame, zcols, method="spearman")
    avg = corrpca.average_corr(mats)
    avg.to_csv(out / "sleeve_corr_spearman.csv")
    pca_res = corrpca.pca(avg)
    pd.DataFrame({"eigenvalue": pca_res["eigenvalues"],
                  "explained": pca_res["explained"],
                  "cumulative": pca_res["cumulative"]},
                 index=[f"PC{i+1}" for i in range(len(zcols))]).to_csv(
        out / "sleeve_pca.csv")
    pairs = corrpca.ranked_pairs(avg).head(10).to_dict("records")
    print("[lab] top sleeve pairs: " +
          ", ".join(f"{p['factor_a']}/{p['factor_b']}={p['corr']:+.2f}"
                    for p in pairs[:5]), flush=True)
    results["sleeve_corr"] = avg.round(4).to_dict()
    results["sleeve_pca_eigenvalues"] = [
        float(v) for v in pca_res["eigenvalues"]]
    results["sleeve_pca_explained"] = [float(v) for v in
                                       pca_res["explained"]]

    results["config"] = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel": str(args.panel),
        "spec": "per-sleeve runs mirror scripts/backtest_panel.py: monthly "
                "rebalance, t+1 execution, 10 bps one-way on both legs, "
                "delist 0.0 (gap) / -0.3 (permanent, Shumway 1997), 1/99 "
                "holding-return winsorization; sleeve weights NOT used "
                "(each sleeve tested standalone)",
        "universe": "per sleeve: tickers with non-NaN sleeve z at "
                    "rebalance (own coverable universe)",
        "regimes": "SPY trailing 21d return sign (up/down); trailing 63d "
                   "realized vol vs median (high/low vol); no VIX in bulk "
                   "data so realized vol is the documented proxy",
        "ic_horizons": "Spearman IC of sleeve z(t) vs forward total return "
                       "over 21/63/126/252 trading days, from adj_close",
    }
    (out / "summary.json").write_text(
        json.dumps(results, default=_jsonable, indent=1))
    print(f"[lab] wrote {out}", flush=True)


if __name__ == "__main__":
    main()
