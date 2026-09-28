"""Quintile spreads: per-date sort on the sector-neutral z-score.

Q5 = most attractive quintile (highest z). Spread = equal-weighted forward
return of Q5 minus Q1. Forward returns are winsorized per date at the
1st/99th percentiles before averaging: the panel's micro-cap tail contains
single-name 21-day moves above +10000%, and equal-weighted means would
otherwise be dominated by a handful of lottery tickets. ICs are unaffected
(rank-based). Cumulative spread is the plain running sum of per-date
spreads (P&L of a monthly-rebalanced dollar-neutral spread).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

N_QUINTILES = 5
RET_WINSOR = (0.01, 0.99)  # cross-sectional winsorization of forward returns


def assign_quintiles(z: pd.Series, n: int = N_QUINTILES) -> pd.Series:
    """Quintile labels 1..n on the z-score; NaN where unassignable.

    ``duplicates="drop"`` collapses tied bins; if fewer than n distinct bins
    survive, the date is left unassigned (caller drops it).
    """
    valid = z.dropna()
    if len(valid) < n * 10:
        return pd.Series(np.nan, index=z.index)
    try:
        q = pd.qcut(valid, n, labels=False, duplicates="drop")
    except (ValueError, TypeError):
        return pd.Series(np.nan, index=z.index)
    if q.nunique() < n:
        return pd.Series(np.nan, index=z.index)
    return (q + 1).reindex(z.index).astype("float")


def winsorize_returns(df: pd.DataFrame, retcol: str,
                      limits: tuple[float, float] = RET_WINSOR) -> pd.Series:
    """Cross-sectional winsorization of forward returns, per date."""
    lo, hi = limits

    def _clip(s: pd.Series) -> pd.Series:
        q = s.quantile([lo, hi])
        if q.isna().any():
            return s
        # Note: no guard for q_lo == q_hi. Clipping is the identity when all
        # values are identical, and it is exactly the lottery-ticket case
        # (>99% identical, a few huge outliers) that needs the clip.
        return s.clip(q.iloc[0], q.iloc[1])

    return (df.groupby("date", observed=True)[retcol].transform(_clip)
            .rename(f"{retcol}_w"))


def quintile_returns(df: pd.DataFrame, zcol: str, retcol: str,
                     n: int = N_QUINTILES) -> pd.DataFrame:
    """Per-date equal-weighted forward return by quintile (winsorized).

    Returns DataFrame indexed by date with columns q1..qn and spread (= qn-q1).
    Dates with unassignable quintiles are skipped.
    """
    df = df.copy()
    retw = f"{retcol}_w"
    df[retw] = winsorize_returns(df, retcol)
    rows = []
    for date, g in df.groupby("date", observed=True):
        q = assign_quintiles(g[zcol], n)
        if q.isna().all():
            continue
        gg = g.assign(_q=q).dropna(subset=["_q", retw])
        if gg["_q"].nunique() < n or len(gg) < n * 10:
            continue
        means = gg.groupby("_q", observed=True)[retw].mean()
        row = {"date": date}
        for i in range(1, n + 1):
            row[f"q{i}"] = float(means.get(float(i), np.nan))
        row["spread"] = row[f"q{n}"] - row["q1"]
        rows.append(row)
    out = pd.DataFrame(rows)
    if len(out):
        out = out.set_index("date").sort_index()
    return out


def spread_summary(qret: pd.DataFrame) -> dict:
    """Mean/std/t-stat/hit-rate of the spread plus Q1/Q5 standalone means."""
    s = qret["spread"].dropna()
    n = len(s)
    base = {"n": n, "q1_mean": float(qret["q1"].mean()),
            "q5_mean": float(qret["q5"].mean()),
            "cumulative": float(s.sum()) if n else np.nan}
    if n < 2:
        return {**base, "mean": np.nan, "std": np.nan,
                "tstat": np.nan, "hit_rate": np.nan}
    mean = float(s.mean())
    std = float(s.std(ddof=1))
    return {
        **base,
        "mean": mean,
        "std": std,
        "tstat": float(mean / (std / np.sqrt(n))) if std > 0 else np.nan,
        "hit_rate": float((s > 0).mean()),
    }


def annual_spreads(qret: pd.DataFrame) -> pd.Series:
    """Mean spread per calendar year (for the report table)."""
    if not len(qret):
        return pd.Series(dtype=float)
    return qret["spread"].groupby(qret.index.year).mean().rename("spread")
