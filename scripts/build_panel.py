#!/usr/bin/env python3
"""Borealis bulk ingest CLI: Intrinio zips -> clean Parquet -> PIT panel.

Example:
    PYTHONPATH=src python scripts/build_panel.py \
        --raw data/raw/intrinio/2026-09-28 \
        --out data/processed/intrinio

Stages (each skipped if its output already exists, unless --rebuild):
    1. prices       bulk price zips -> prices_clean.parquet
    2. calcs        CALCULATIONS zips -> fundamentals_slim.parquet
    3. panel        PIT (date, ticker) panel -> panel/year=YYYY/*.parquet

Raw zips are never modified. Licensed data stays local.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from borealis.ingest import intrinio_bulk, panel  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(prog="build_panel")
    ap.add_argument("--raw", required=True, help="dir with Intrinio bulk zips")
    ap.add_argument("--out", required=True, help="output dir for Parquet tables")
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild even if outputs exist")
    ap.add_argument("--ticker-batch", type=int, default=2500)
    args = ap.parse_args()

    raw, out = Path(args.raw), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    qdir = out / "_quarantine"
    report: dict = {"raw": str(raw), "out": str(out)}

    prices_path = out / "prices_clean.parquet"
    if prices_path.exists() and not args.rebuild:
        print(f"[1/3] prices: reusing {prices_path}")
        report["prices"] = {"reused": True}
    else:
        print("[1/3] prices: streaming bulk zips ...", flush=True)
        report["prices"] = intrinio_bulk.load_prices(raw, prices_path, qdir)

    calcs_path = out / "fundamentals_slim.parquet"
    if calcs_path.exists() and not args.rebuild:
        print(f"[2/3] calculations: reusing {calcs_path}")
        report["calculations"] = {"reused": True}
    else:
        print("[2/3] calculations: streaming bulk zips ...", flush=True)
        report["calculations"] = intrinio_bulk.load_calculations(raw, calcs_path, qdir)

    revenue_path = out / "revenue_slim.parquet"
    if revenue_path.exists() and not args.rebuild:
        print(f"[2b/3] revenue: reusing {revenue_path}")
        report["revenue"] = {"reused": True}
    else:
        print("[2b/3] revenue: streaming income-statement zips ...", flush=True)
        report["revenue"] = intrinio_bulk.load_income_statements(raw, revenue_path,
                                                                 qdir)

    print("[3/3] panel: point-in-time join ...", flush=True)
    companies = intrinio_bulk.load_companies(raw)
    companies.to_parquet(out / "companies.parquet", index=False)
    report["companies"] = {"rows": len(companies),
                           "sectors": int(companies["sector"].nunique())}
    panel_dir = out / "panel"
    if (panel_dir / "year=2020").exists() and not args.rebuild:
        print(f"panel: reusing {panel_dir}")
        report["panel"] = {"reused": True}
    else:
        report["panel"] = panel.build_panel(prices_path, calcs_path,
                                            companies, panel_dir,
                                            ticker_batch=args.ticker_batch,
                                            revenue_path=revenue_path)

    rep_path = out / "_load_report.json"
    rep_path.write_text(json.dumps(report, indent=1, default=str))
    print(f"\nwrote {rep_path}")
    print(json.dumps(report, indent=1, default=str)[:1500])


if __name__ == "__main__":
    main()
