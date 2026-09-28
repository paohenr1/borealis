"""Portfolio construction: quintile formation, caps, turnover control."""
from __future__ import annotations

import numpy as np
import pandas as pd


def form_quintiles(scores: pd.Series, n: int = 5) -> pd.Series:
    """Map composite scores to quintile labels 1..n (1 = least attractive)."""
    return pd.qcut(scores, n, labels=False, duplicates="drop").add(1).rename("quintile")


def apply_caps(weights: pd.Series, sectors: pd.Series,
               max_position: float = 0.05,
               max_sector: float = 0.30) -> pd.Series:
    """Cap single-name and sector weights, renormalizing to sum to 1."""
    w = weights.clip(upper=max_position)
    for _ in range(50):  # iterate sector caps to convergence
        sec_w = w.groupby(sectors).sum()
        over = sec_w[sec_w > max_sector]
        if over.empty:
            break
        scale = sectors.map(over / max_sector).fillna(1.0)
        w = w / scale
    total = w.sum()
    w = w / total if total else w
    return w.rename("weight")


def turnover(old: pd.Series, new: pd.Series) -> float:
    """One-way turnover between two weight vectors (aligned on union of names)."""
    idx = old.index.union(new.index)
    return float(0.5 * (new.reindex(idx, fill_value=0.0) - old.reindex(idx, fill_value=0.0)).abs().sum())
