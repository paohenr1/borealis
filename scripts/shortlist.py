#!/usr/bin/env python3
"""Borealis attention filter: turn a ranked universe CSV into a monthly
research shortlist.

Reads the latest scores CSV (default: most recent
data/processed/scores_live_*.csv), takes the top N names, and writes a
readable shortlist with sleeve attribution ("what is driving this rank"),
key multiples, and new-vs-last-month flags.

Usage:
    PYTHONPATH=src python scripts/shortlist.py [--top 15]
        [--scores data/processed/scores_live_2026-09-30.csv]
        [--out data/processed/shortlist_2026-09-30.md]

The shortlist is the attention filter: which companies deserve Henry's
research hours this month. It is not a buy list -- the lab found no
large-cap edge, so the shortlist makes no promise that #1 beats #200.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
from datetime import date
from pathlib import Path

import pandas as pd

LIVE_W = {"z_value": 0.20, "z_momentum": 0.20, "z_lowvol": 0.10}
SLEEVE_LABEL = {"z_value": "value", "z_momentum": "momentum", "z_lowvol": "lowvol"}


def _latest_scores() -> Path:
    cands = sorted(glob.glob("data/processed/scores_live_*.csv"))
    if not cands:
        raise FileNotFoundError("no data/processed/scores_live_*.csv found")
    return Path(cands[-1])


def _prev_shortlist_tickers(out_path: Path) -> set[str]:
    """Tickers on the most recent previous shortlist, for new-entry flags."""
    prev = sorted(
        p for p in glob.glob("data/processed/shortlist_*.md")
        if Path(p) != out_path
    )
    if not prev:
        return set()
    tickers: set[str] = set()
    for line in Path(prev[-1]).read_text().splitlines():
        m = re.match(r"\|\s*\d+\s*\|\s*([A-Z][A-Z0-9.\-]*)\s*\|", line)
        if m:
            tickers.add(m.group(1))
    return tickers


def _fmt_mcap(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v >= 1e12:
        return f"${v/1e12:.1f}T"
    if v >= 1e9:
        return f"${v/1e9:.0f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    return "—"


def _fmt(x, nd=1) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    if pd.isna(x):
        return "—"
    return f"{x:+.{nd}f}" if nd else f"{x:.{nd}f}"


def main() -> None:
    ap = argparse.ArgumentParser(prog="borealis-shortlist")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--scores", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    scores_path = Path(args.scores) if args.scores else _latest_scores()
    asof = scores_path.stem.replace("scores_live_", "")
    out_path = Path(args.out) if args.out else Path(f"data/processed/shortlist_{asof}.md")

    df = pd.read_csv(scores_path)
    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)
    top = df.head(args.top)

    prev_tickers = _prev_shortlist_tickers(out_path)

    lines = [
        f"# Borealis research shortlist — {asof}",
        "",
        f"Top {len(top)} of {len(df)} ranked names "
        f"(weights: value 0.20 / momentum 0.20 / 126d low-vol 0.10).",
        "Attention filter, not a buy list: the lab found no large-cap edge,",
        "so this orders where research hours go, not what to buy.",
        "",
        "| # | ticker | company | sector | score | driver | price | mcap | P/E | P/S | 52w |",
        "|---|--------|---------|--------|-------|--------|-------|------|-----|-----|-----|",
    ]
    for _, r in top.iterrows():
        # driver = sleeve with the largest weighted contribution
        contribs = {c: LIVE_W[c] * r[c] for c in LIVE_W if pd.notna(r[c])}
        driver = SLEEVE_LABEL[max(contribs, key=contribs.get)] if contribs else "—"
        new = " ★" if r["ticker"] not in prev_tickers and prev_tickers else ""
        w52 = r.get("pct_below_52w_high", float("nan"))
        try:
            w52s = f"{abs(float(w52))*100:.0f}% off hi" if pd.notna(w52) else "—"
        except (TypeError, ValueError):
            w52s = "—"
        lines.append(
            f"| {int(r['rank'])} | {r['ticker']}{new} | {str(r['company'])[:30]} "
            f"| {r['sector']} | {_fmt(r['composite'], 2)} | {driver} "
            f"| {r['price']:.2f} | {_fmt_mcap(r['market_cap'])} "
            f"| {_fmt(r['pe_ratio'], 1)} | {_fmt(r['ps_ratio'], 1)} | {w52s} |"
        )

    lines += [
        "",
        "★ = new since last shortlist." if prev_tickers else "First shortlist in the series.",
        "",
        "## Sleeve detail (z-scores; quality shown as diagnostic)",
        "",
        "| ticker | z_value | z_momentum | z_lowvol | z_quality (diag) |",
        "|--------|---------|------------|----------|------------------|",
    ]
    for _, r in top.iterrows():
        lines.append(
            f"| {r['ticker']} | {_fmt(r['z_value'], 2)} | {_fmt(r['z_momentum'], 2)} "
            f"| {_fmt(r['z_lowvol'], 2)} | {_fmt(r['z_quality'], 2)} |"
        )
    lines += [
        "",
        "_Log conclusions in notes/research_log.md — ticker, thesis in one line,",
        "verdict (pass / watch / deep-dive). The log is what closes the loop",
        "back to the lab._",
        "",
    ]
    out_path.write_text("\n".join(lines))
    print(f"wrote {out_path} ({len(top)} names)")


if __name__ == "__main__":
    main()
