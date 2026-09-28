#!/usr/bin/env python3
"""Borealis CLI: score a Ranks & Earnings universe file.

Example:
    PYTHONPATH=src python scripts/rank.py \
        --input data/raw/ranks_earnings_2026-09-22.xlsx \
        --asof 2026-09-22 --top 5
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


def main() -> None:
    ap = argparse.ArgumentParser(prog="borealis")
    ap.add_argument("--input", required=True, help="Ranks & Earnings workbook")
    ap.add_argument("--asof", required=True, help="as-of date, e.g. 2026-09-22")
    ap.add_argument("--config-dir", default="config")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--out", default="data/processed/scores.csv")
    args = ap.parse_args()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fcfg = yaml.safe_load(open(Path(args.config_dir) / "factors.yaml"))
        scfg = fcfg["scoring"]

        df = load_universe(args.input)
        validate_universe(df, args.asof)

        df["value"] = factors.value.value_score(df)
        df["quality"] = factors.quality.quality_score(df)
        df["growth"] = factors.growth.growth_score(df)
        df["momentum"] = factors.momentum.momentum_score(df)
        df["lowvol"] = factors.lowvol.lowvol_score(df)

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
