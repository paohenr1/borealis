#!/usr/bin/env python3
"""Validate the EXACT live quality sleeve on the extended panel (2026-09-30).

The 2026-09-30 panel extension added gross_margin (INDU calculations),
revenue (TTM totalrevenue from income statements), fcf_margin (= fcf /
revenue, same formula as universe_live.py) and debt_to_equity to the
point-in-time panel. The live quality sleeve is now fully panel-representable:

    roe, roa, gross_margin, profit_margin, fcf_margin,
    debt_to_equity, debt_ebitda, interest_coverage

This script compares that EXACT sleeve against the previously validated
APPROXIMATION (roe, roa, profit_margin, fcf, debt_ebitda, leverage,
interest_coverage) using the factor lab's own machinery (month-end
rebalances, sector-neutral winsorized z-scores, rank IC vs 21d/63d forward
returns, quintile spreads), and reports coverage of the new tags on the
broad panel and the live 518 universe.

Usage:
    PYTHONPATH=src python3 scripts/validate_quality_exact.py \
        --panel data/processed/intrinio/panel
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.lab import composite, ic, preprocess, quintiles  # noqa: E402
from borealis.lab.run import HORIZONS, load_lab_frame, month_end_dates  # noqa: E402

APPROX = ["roe", "roa", "profit_margin", "fcf", "debt_ebitda",
          "leverage", "interest_coverage"]
EXACT = ["roe", "roa", "gross_margin", "profit_margin", "fcf_margin",
         "debt_to_equity", "debt_ebitda", "interest_coverage"]
NEW_TAGS = ["gross_margin", "revenue", "fcf_margin", "debt_to_equity"]


def sleeve_stats(frame: pd.DataFrame, members: list[str],
                 min_n: int = 30) -> dict:
    """IC + quintile spread for the mean-z of `members` (pairwise-complete)."""
    zcols = [f"z_{m}" for m in members if f"z_{m}" in frame.columns]
    sub = frame.dropna(subset=zcols, how="all").copy()
    sub["sleeve_z"] = sub[zcols].mean(axis=1, skipna=True)
    out: dict = {"members": members, "n_factors": len(zcols)}
    for h, retcol in HORIZONS.items():
        valid = sub.dropna(subset=["sleeve_z", retcol])
        counts = valid.groupby("date", observed=True).size()
        ok = counts[counts >= min_n].index
        s = ic.ic_series(valid[valid["date"].isin(ok)], "sleeve_z", retcol)
        summ = ic.ic_summary(s)
        qret = quintiles.quintile_returns(valid[valid["date"].isin(ok)],
                                          "sleeve_z", retcol)
        spread = quintiles.spread_summary(qret)
        out[f"ic_{h}"] = {k: float(v) for k, v in summ.items()
                          if isinstance(v, (int, float))}
        out[f"spread_{h}"] = {k: float(v) for k, v in spread.items()
                              if isinstance(v, (int, float))}
        print(f"  h={h}d: IC={summ['mean']:+.4f} (t={summ['tstat']:+.2f}, "
              f"hit={summ['hit_rate']:.0%}, n={summ['n']}), "
              f"spread={spread['mean']:+.2%} (t={spread['tstat']:+.2f})",
              flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--universe", default="data/raw/universe_520.csv")
    args = ap.parse_args()
    panel_dir = Path(args.panel)

    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    missing = [c for c in NEW_TAGS if c not in dataset.schema.names]
    if missing:
        sys.exit(f"panel missing new columns {missing} -- rebuild it first")

    all_dates = sorted(
        t.as_py() for t in dataset.to_table(columns=["date"]).column("date").unique()
    )
    all_dates = [pd.Timestamp(d) for d in all_dates]
    rebal = month_end_dates(all_dates)

    factors = sorted(set(APPROX + EXACT))
    # revenue is a diagnostic column (not z-scored), load it alongside
    frame = load_lab_frame(panel_dir, rebal, factors + ["revenue"],
                           need_returns=True)
    print(f"[qval] rebalance frame: {len(frame):,} rows x {len(rebal)} dates",
          flush=True)

    out: dict = {}
    print("[qval] broad-panel factor coverage (rebalance frame):")
    for f in NEW_TAGS:
        cov = float(frame[f].notna().mean())
        out[f"coverage_{f}"] = cov
        print(f"    {f:<14} {cov:.1%}")

    # live-518 coverage at the latest rebalance date
    uni = pd.read_csv(args.universe)
    live_tickers = set(uni["ticker"].astype(str))
    latest = frame[frame["date"] == frame["date"].max()]
    live = latest[latest["ticker"].isin(live_tickers)]
    print(f"[qval] live-518 coverage @ {frame['date'].max().date()} "
          f"(n={len(live)} tickers in panel):")
    for f in NEW_TAGS:
        cov = float(live[f].notna().mean()) if len(live) else float("nan")
        out[f"live_coverage_{f}"] = cov
        print(f"    {f:<14} {cov:.1%}")

    frame = preprocess.add_lab_zscores(frame, factors)

    print("[qval] APPROX quality sleeve (old lab definition):")
    out["approx"] = sleeve_stats(frame, APPROX)
    print("[qval] EXACT quality sleeve (live definition):")
    out["exact"] = sleeve_stats(frame, EXACT)

    # redundancy: max |corr| of each new factor vs the old quality peers
    zcols = [f"z_{f}" for f in factors if f"z_{f}" in frame.columns]
    corrs = []
    for _, g in frame.dropna(subset=zcols).groupby("date", observed=True):
        if len(g) >= 30:
            corrs.append(g[zcols].corr())
    if corrs:
        avg = pd.concat(corrs).groupby(level=0).mean()
        print("[qval] max |avg corr| of new factors vs old quality peers:")
        peers = [f"z_{f}" for f in APPROX]
        for f in ["gross_margin", "fcf_margin", "debt_to_equity"]:
            zc = f"z_{f}"
            if zc in avg.index:
                mx = avg.loc[zc, peers].abs().max()
                out[f"max_corr_{f}"] = float(mx)
                print(f"    {f:<14} {mx:.3f}")

    rep = Path("data/processed/quality_exact_validation.json")
    rep.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {rep}")


if __name__ == "__main__":
    main()
