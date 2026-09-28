"""Tear sheets and factor attribution: show WHY a stock ranks where it does."""
from __future__ import annotations

import pandas as pd

DISPLAY_COLS = ["rank", "ticker", "company", "sector", "composite",
                "price", "pe_ratio", "ps_ratio", "peg_ratio"]


def top_n_table(scored: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    cols = [c for c in DISPLAY_COLS if c in scored.columns]
    return (scored.sort_values(["sector", "rank"])
                  .groupby("sector").head(n)[cols]
                  .reset_index(drop=True))


def factor_attribution(scored: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Per-factor z-score contribution for one ticker (composite = weighted sum)."""
    row = scored.loc[scored["ticker"] == ticker]
    if row.empty:
        raise KeyError(f"ticker {ticker} not in scored universe")
    row = row.iloc[0]
    z_cols = sorted([c for c in scored.columns if c.startswith("z_")])
    attrib = pd.DataFrame({
        "factor": [c[2:] for c in z_cols],
        "z_score": [row[c] for c in z_cols],
    })
    return attrib.sort_values("z_score", ascending=False).reset_index(drop=True)


def _fmt_num(x, fmt: str) -> str:
    return "—" if pd.isna(x) else format(float(x), fmt)


def format_top_n(scored: pd.DataFrame, n: int = 5) -> str:
    """Human-readable ranking: one block per sector, aligned columns.

    Numbers are rounded for display only — the CSV keeps full precision.
    """
    table = top_n_table(scored, n)
    header = f"{'rank':>4}  {'ticker':<8} {'company':<28} {'score':>7} {'price':>10} {'P/E':>7} {'P/S':>7} {'PEG':>6}"
    lines = []
    for sector, grp in table.groupby("sector", sort=False):
        title = sector.replace("_", " ").title()
        lines.append(f"\n{title} — top {len(grp)}")
        lines.append(header)
        for _, r in grp.iterrows():
            company = str(r["company"])[:28]
            lines.append(
                f"{int(r['rank']):>4}  {str(r['ticker']):<8} {company:<28} "
                f"{_fmt_num(r['composite'], '+.2f'):>7} "
                f"{_fmt_num(r['price'], ',.2f'):>10} "
                f"{_fmt_num(r['pe_ratio'], '.1f'):>7} "
                f"{_fmt_num(r['ps_ratio'], '.1f'):>7} "
                f"{_fmt_num(r['peg_ratio'], '.2f'):>6}"
            )
    return "\n".join(lines)
