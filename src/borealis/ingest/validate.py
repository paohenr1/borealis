"""Validation checks run on every ingest. Fail fast, fail loud."""
from __future__ import annotations

import pandas as pd

REQUIRED_COLS = [
    "ticker", "company", "sector", "currency", "price",
    "pe_ratio", "ps_ratio", "peg_ratio", "sales_growth_q",
    "trailing_beta", "pct_above_52w_low",
]


def validate_universe(df: pd.DataFrame, asof: str) -> None:
    """Raise ValueError listing every problem found. Returns None on success."""
    errors: list[str] = []

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        errors.append(f"missing columns: {missing}")

    if df.empty:
        errors.append("universe is empty")
        raise ValueError("; ".join(errors))

    n_dupes = int(df.duplicated("ticker").sum())
    if n_dupes:
        dupes = df.loc[df.duplicated("ticker"), "ticker"].unique().tolist()
        errors.append(f"{n_dupes} duplicate tickers, e.g. {dupes[:5]}")

    n_noprice = int(df["price"].isna().sum()) if "price" in df.columns else 0
    if n_noprice:
        errors.append(f"{n_noprice} rows missing price")

    for col in ["pe_ratio", "ps_ratio", "peg_ratio"]:
        if col in df.columns:
            n_zero = int((df[col] == 0).sum())
            if n_zero:
                # Informational: zeros are quarantined as missing downstream.
                print(f"[validate] {n_zero} zero values in {col} -> treated as missing, not cheap")

    n_sectors = int(df["sector"].nunique()) if "sector" in df.columns else 0
    print(f"[validate] asof={asof} rows={len(df)} sectors={n_sectors} tickers={df['ticker'].nunique()}")

    _flag_suspicious(df)

    if errors:
        raise ValueError("; ".join(errors))


def _flag_suspicious(df: pd.DataFrame, limit: int = 15) -> None:
    """Flag implausible-but-not-impossible values. Warns only — never raises.

    Zeros are quarantined as missing downstream and structural problems fail
    loud above; this catches the middle ground: typos, stale prices, and
    vendor errors that would otherwise flow silently into scores
    (winsorization only caps their influence, it does not flag them).
    """
    flags: list[str] = []

    def check(col: str, mask, reason: str) -> None:
        if col not in df.columns:
            return
        hit = df.loc[mask.fillna(False) if hasattr(mask, "fillna") else mask]
        for _, r in hit.iterrows():
            flags.append(f"{r['ticker']}: {col}={r[col]} ({reason})")

    check("pe_ratio", df["pe_ratio"] > 200, "P/E > 200, likely bad data")
    check("peg_ratio", df["peg_ratio"] > 20, "PEG > 20, likely bad data")
    check("ps_ratio", df["ps_ratio"] > 50, "P/S > 50, likely bad data")
    check("trailing_beta", df["trailing_beta"].abs() > 3, "|beta| > 3, likely bad data")
    for col in ["price", "low_52w", "high_52w"]:
        if col not in df.columns:
            break
    else:
        bad = (df["price"] < df["low_52w"]) | (df["price"] > df["high_52w"])
        check("price", bad, "price outside 52-week range (stale price or bad high/low)")

    if flags:
        print(f"[validate] {len(flags)} suspicious values — flagged, still scored; verify before trusting:")
        for f in flags[:limit]:
            print(f"    ! {f}")
        if len(flags) > limit:
            print(f"    ! ... and {len(flags) - limit} more")
