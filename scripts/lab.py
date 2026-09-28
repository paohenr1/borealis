#!/usr/bin/env python3
"""Borealis factor lab CLI.

Modes:
  efficacy  ICs, quintile spreads, signal half-life (default)
  corrpca   factor correlation + PCA (+ redundancy analysis)
  all       run both

Example:
    PYTHONPATH=src python scripts/lab.py --mode corrpca \
        --panel data/processed/intrinio/panel \
        --out reports

Reads the point-in-time panel (read-only) and writes Markdown reports plus
JSON results under --out. Use --max-factors for a quick smoke run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.lab import run as lab_run  # noqa: E402
from borealis.lab import run_corrpca  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(prog="lab")
    ap.add_argument("--mode", choices=["efficacy", "corrpca", "all"],
                    default="efficacy")
    ap.add_argument("--panel", default="data/processed/intrinio/panel",
                    help="PIT panel dir (year=YYYY/*.parquet)")
    ap.add_argument("--out", default="reports",
                    help="output dir for the Markdown report + JSON")
    ap.add_argument("--factors", nargs="*", default=None,
                    help="subset of factor columns (default: all in panel)")
    ap.add_argument("--max-factors", type=int, default=None,
                    help="cap on factor count (quick smoke runs)")
    ap.add_argument("--efficacy-json", default=None,
                    help="efficacy lab JSON (for |IC t-stat| keeper priority)")
    args = ap.parse_args()

    if args.mode in ("efficacy", "all"):
        out = lab_run.run_lab(args.panel, args.out, factors=args.factors,
                              max_factors=args.max_factors)
        print(f"\nreport: {out['report_md']}")
    if args.mode in ("corrpca", "all"):
        out = run_corrpca.run_corrpca(
            args.panel, args.out, factors=args.factors,
            max_factors=args.max_factors, efficacy_json=args.efficacy_json)
        print(f"\nreport: {out['report_md']}")


if __name__ == "__main__":
    main()
