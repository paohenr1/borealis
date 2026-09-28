"""Composite scoring.

Pipeline per factor column (each already oriented higher = better):
  1. winsorize at +/- sigma within sector (outlier control)
  2. z-score within sector (sector-neutral, magnitude-preserving)
  3. weighted average -> composite; rank 1 = most attractive in sector

Factor columns that are entirely NaN (e.g. quality before its data
exists) are skipped and weights renormalized over the rest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def winsorize(s: pd.Series, sigma: float = 3.0) -> pd.Series:
    mu = s.mean(skipna=True)
    sd = s.std(skipna=True)
    if pd.isna(sd) or sd == 0:
        return s
    return s.clip(mu - sigma * sd, mu + sigma * sd)


def sector_zscore(df: pd.DataFrame, col: str, sector_col: str = "sector",
                  sigma: float = 3.0) -> pd.Series:
    w = df.groupby(sector_col)[col].transform(lambda s: winsorize(s, sigma))
    mu = w.groupby(df[sector_col]).transform("mean")
    sd = w.groupby(df[sector_col]).transform("std").replace(0, np.nan)
    return (w - mu) / sd


def composite_score(df: pd.DataFrame, factor_weights: dict[str, float],
                    sector_col: str = "sector", sigma: float = 3.0,
                    rank_method: str = "min") -> pd.DataFrame:
    active = {c: w for c, w in factor_weights.items()
              if c in df.columns and df[c].notna().any()}
    skipped = sorted(set(factor_weights) - set(active))
    if skipped:
        print(f"[scoring] skipping all-NaN factors: {skipped} (weights renormalized)")
    if not active:
        raise ValueError("No active factor columns to score.")

    out = df.copy()
    total = sum(active.values())
    comp = pd.Series(0.0, index=df.index)
    for col, w in active.items():
        z = sector_zscore(df, col, sector_col, sigma).fillna(0.0)
        comp += (w / total) * z
        out[f"z_{col}"] = z
    out["composite"] = comp
    out["rank"] = (
        out.groupby(sector_col)["composite"]
        .rank(ascending=False, method=rank_method)
        .astype("Int64")
    )
    return out
