"""Load the Ranks & Earnings workbook's UNIVERSE sheet.

The sheet is a stack of per-sector blocks. Each block starts with a header
row whose first cell is "(n)" and whose third cell names the sector; data
rows follow until a blank row.

Columns are assigned POSITIONALLY because the sheet reuses names
("PEG Ratio" and "Trailing Beta" each appear twice: raw metric + sub-rank).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Positional schema for the 27-column block layout.
ORDERED_COLS = [
    "n", "i", "company", "ticker", "currency", "last_qtr", "price",
    "market_cap", "high_52w", "low_52w", "pct_below_52w_high",
    "pct_above_52w_low", "ps_ratio", "pe_ratio", "sales_growth_q",
    "peg_ratio", "trailing_beta", "inovestor_rank",
    # sub-rank columns (kept for audit, not used in scoring v0.1)
    "rank_52w_low", "rank_ps", "rank_pe", "rank_sales_growth",
    "rank_peg", "rank_beta", "rank_inovestor", "total_rank", "rank_of_rank",
]

SECTOR_SLUGS = {
    "Consumer Discretionary": "consumer_discretionary",
    "Consumer Staples": "consumer_staples",
    "Energy": "energy",
    "Financials": "financials",
    "Health Care": "health_care",
    "Industrials": "industrials",
    "Materials": "materials",
    "Real Estate": "real_estate",
    "Technology": "technology",
    "Telecommunication": "telecommunication",
    "Utilities": "utilities",
}

NUMERIC_COLS = [
    "price", "market_cap", "high_52w", "low_52w",
    "pct_below_52w_high", "pct_above_52w_low",
    "ps_ratio", "pe_ratio", "sales_growth_q", "peg_ratio",
    "trailing_beta", "inovestor_rank",
]


def _read_blocks(path: str | Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="UNIVERSE", header=None)
    blocks: list[pd.DataFrame] = []
    i, n = 0, len(raw)
    while i < n:
        first = raw.iloc[i, 0]
        if isinstance(first, str) and first.strip() == "(n)":
            sector_raw = str(raw.iloc[i, 2]).strip()
            i += 1
            rows = []
            while i < n and pd.notna(raw.iloc[i, 0]):
                cell0 = raw.iloc[i, 0]
                if isinstance(cell0, str) and cell0.strip() == "(n)":
                    break
                rows.append(raw.iloc[i].tolist())
                i += 1
            block = pd.DataFrame(rows)
            width = len(ORDERED_COLS)
            if block.shape[1] < width:  # ragged trailing cells -> pad
                for j in range(block.shape[1], width):
                    block[j] = np.nan
            block = block.iloc[:, :width]
            block.columns = ORDERED_COLS
            block["sector_raw"] = sector_raw
            blocks.append(block)
        else:
            i += 1
    if not blocks:
        raise ValueError("No sector blocks found — is this the UNIVERSE sheet?")
    return pd.concat(blocks, ignore_index=True)


def load_universe(path: str | Path) -> pd.DataFrame:
    """Load and normalize the universe into one tidy DataFrame."""
    df = _read_blocks(path)

    df["sector"] = df["sector_raw"].map(SECTOR_SLUGS)
    unmapped = df.loc[df["sector"].isna(), "sector_raw"].unique()
    if len(unmapped):
        raise ValueError(f"Unmapped sector names: {list(unmapped)}")

    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["company"] = df["company"].astype(str).str.strip()
    return df.reset_index(drop=True)
