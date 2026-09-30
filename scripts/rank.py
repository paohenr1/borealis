#!/usr/bin/env python3
"""Borealis CLI: score a Ranks & Earnings universe file -- or the live
Intrinio-backed universe.

Workbook path (unchanged):
    PYTHONPATH=src python scripts/rank.py \
        --input data/raw/ranks_earnings_2026-09-22.xlsx \
        --asof 2026-09-22 --top 5

Live path (no spreadsheet; ~520 index constituents from Intrinio bulk):
    PYTHONPATH=src python scripts/rank.py \
        --live --asof 2026-09-29 --top 5 \
        --out data/processed/scores_live_2026-09-29.csv
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis import factors, scoring
from borealis.ingest.loader import load_universe
from borealis.ingest.validate import validate_universe
from borealis.reporting.tearsheet import format_top_n


def _latest_bulk_dir() -> Path:
    base = Path("data/raw/intrinio")
    dated = sorted(p for p in base.iterdir() if p.is_dir())
    if not dated:
        raise FileNotFoundError(f"no bulk download dirs under {base}")
    return dated[-1]


def main() -> None:
    ap = argparse.ArgumentParser(prog="borealis")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="Ranks & Earnings workbook (.xlsx)")
    src.add_argument("--live", action="store_true",
                     help="build the universe live from Intrinio bulk data")
    ap.add_argument("--universe-csv", default="data/raw/universe_520.csv",
                    help="ticker list for --live")
    ap.add_argument("--raw-dir", default=None,
                    help="Intrinio bulk dir for --live "
                         "(default: latest under data/raw/intrinio/)")
    ap.add_argument("--asof", required=True, help="as-of date, e.g. 2026-09-22")
    ap.add_argument("--config-dir", default="config")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--out", default="data/processed/scores.csv")
    args = ap.parse_args()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fcfg = yaml.safe_load(open(Path(args.config_dir) / "factors.yaml"))
        scfg = fcfg["scoring"]

        if args.live:
            from borealis.ingest.universe_live import build_live_universe
            raw_dir = Path(args.raw_dir) if args.raw_dir else _latest_bulk_dir()
            df, coverage = build_live_universe(args.universe_csv, raw_dir)
            print(f"[rank] live snapshot={coverage['snapshot_price_date']} "
                  f"tickers={len(df)} sectors={df['sector'].nunique()} "
                  f"excluded_no_price={coverage['excluded_no_price']}",
                  file=sys.stderr)
            nan = coverage["nan_counts"]
            print(f"[rank] NaN counts: " +
                  ", ".join(f"{k}={v}" for k, v in sorted(nan.items())),
                  file=sys.stderr)
        else:
            df = load_universe(args.input)
        validate_universe(df, args.asof)

        df["value"] = factors.value.value_score(df)
        df["quality"] = factors.quality.quality_score(df)
        df["growth"] = factors.growth.growth_score(df)
        df["momentum"] = factors.momentum.momentum_score(df)
        df["lowvol"] = factors.lowvol.lowvol_score(df)
        df["size"] = factors.size.size_score(df)

        weights = {f: c["weight"] for f, c in fcfg["factors"].items()}
        scored = scoring.composite.composite_score(
            df, weights, sector_col=scfg["neutralize_by"],
            sigma=scfg["winsorize_sigma"], rank_method=scfg["rank_method"],
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(out, index=False)

    print(format_top_n(scored, args.top))
    print(f"\nwrote {out} ({len(scored)} rows)")


if __name__ == "__main__":
    main()
