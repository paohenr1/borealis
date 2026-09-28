"""Information coefficients: cross-sectional rank IC per factor per date.

For each rebalance date, the Spearman rank correlation between the
sector-neutral factor z-score at date t and the forward total return after t.
Point-in-time safe by construction: z(t) only ever meets ret_fwd(t -> t+h).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rank_ic(z: pd.Series, fwd: pd.Series, min_n: int = 30) -> float:
    """Spearman rank IC = Pearson correlation of cross-sectional ranks."""
    df = pd.DataFrame({"z": z, "f": fwd}).dropna()
    if len(df) < min_n:
        return np.nan
    if df["z"].nunique() < 2 or df["f"].nunique() < 2:
        return np.nan
    return float(df["z"].rank().corr(df["f"].rank(), method="pearson"))


def ic_series(df: pd.DataFrame, zcol: str, retcol: str,
              min_n: int = 30) -> pd.Series:
    """Per-date rank IC series (index = date)."""
    return (
        df.groupby("date", observed=True)
        .apply(lambda g: rank_ic(g[zcol], g[retcol], min_n))
        .rename(f"ic_{zcol}")
        .dropna()
    )


def ic_summary(ics: pd.Series) -> dict:
    """Mean IC, std, t-stat, hit rate (% of dates with IC > 0), N."""
    ics = ics.dropna()
    n = len(ics)
    if n < 2:
        return {"n": n, "mean": np.nan, "std": np.nan,
                "tstat": np.nan, "hit_rate": np.nan}
    mean = float(ics.mean())
    std = float(ics.std(ddof=1))
    tstat = mean / (std / np.sqrt(n)) if std > 0 else np.nan
    return {
        "n": n,
        "mean": mean,
        "std": std,
        "tstat": float(tstat),
        "hit_rate": float((ics > 0).mean()),
    }
