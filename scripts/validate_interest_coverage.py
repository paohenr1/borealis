#!/usr/bin/env python3
"""Focused lab validation for interest_coverage (added 2026-09-30).

Reuses the factor lab's own machinery (month-end rebalances, sector-neutral
winsorized z-scores, rank IC vs 21d/63d forward returns, quintile spreads) to
answer: does interest coverage predict, and is it redundant with the quality
factors the panel already had (debt_ebitda, leverage, roe, roa, profit_margin,
fcf)?

Usage:
    PYTHONPATH=src python3 scripts/validate_interest_coverage.py \
        --panel data/processed/intrinio/panel
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.lab import ic, preprocess, quintiles  # noqa: E402
from borealis.lab.run import HORIZONS, load_lab_frame, month_end_dates  # noqa: E402

TARGET = "interest_coverage"
PEERS = ["roe", "roa", "profit_margin", "debt_ebitda", "leverage", "fcf"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    args = ap.parse_args()
    panel_dir = Path(args.panel)

    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    if TARGET not in dataset.schema.names:
        sys.exit(f"panel has no {TARGET!r} column -- rebuild it first")
    all_dates = sorted(
        t.as_py() for t in dataset.to_table(columns=["date"]).column("date").unique()
    )
    all_dates = [pd.Timestamp(d) for d in all_dates]
    rebal = month_end_dates(all_dates)

    factors = [TARGET] + PEERS
    frame = load_lab_frame(panel_dir, rebal, factors, need_returns=True)
    cov = frame[TARGET].notna().mean()
    print(f"[icov] rebalance frame: {len(frame):,} rows x {len(rebal)} dates, "
          f"{TARGET} coverage={cov:.1%}", flush=True)
    frame = preprocess.add_lab_zscores(frame, factors)

    zc = f"z_{TARGET}"
    out: dict = {"coverage": float(cov)}
    for h, retcol in HORIZONS.items():
        valid = frame.dropna(subset=[zc, retcol])
        counts = valid.groupby("date", observed=True).size()
        ok_dates = counts[counts >= 30].index
        sub = frame[frame["date"].isin(ok_dates)]
        ics = ic.ic_series(sub, zc, retcol)
        summ = ic.ic_summary(ics)
        qret = quintiles.quintile_returns(sub, zc, retcol)
        spread = quintiles.spread_summary(qret)
        out[f"ic_{h}"] = {k: float(v) for k, v in summ.items()
                          if isinstance(v, (int, float))}
        out[f"spread_{h}"] = {k: float(v) for k, v in spread.items()
                              if isinstance(v, (int, float))}
        print(f"[icov] h={h}d: IC={summ['mean']:+.4f} (t={summ['tstat']:+.2f}, "
              f"hit={summ['hit_rate']:.0%}, n={summ['n']}), "
              f"spread={spread['mean']:+.2%} (t={spread['tstat']:+.2f})",
              flush=True)

    # Redundancy: average cross-sectional correlation of the z-scores.
    zcols = [f"z_{f}" for f in factors]
    corrs = []
    for _, g in frame.dropna(subset=zcols).groupby("date", observed=True):
        if len(g) >= 30:
            corrs.append(g[zcols].corr())
    avg_corr = pd.concat(corrs).groupby(level=0).mean() if corrs else pd.DataFrame()
    print(f"\n[icov] avg cross-sectional corr vs {TARGET} (n={len(corrs)} dates):")
    if not avg_corr.empty:
        s = avg_corr.loc[zc].drop(zc).sort_values(ascending=False)
        for name, v in s.items():
            print(f"    {name:<16} {v:+.3f}")

    rep = Path("data/processed/interest_coverage_validation.json")
    import json
    rep.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {rep}")


if __name__ == "__main__":
    main()
