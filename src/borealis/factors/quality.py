"""Quality factor: profitable, cash-generative, conservatively financed.

Higher = better. Currently the Ranks & Earnings feed has no ROE / FCF /
leverage columns, so this module degrades gracefully to NaN (zero weight in
the composite) until those fields are added. Add them and it just works.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

# metric -> higher_better?
QUALITY_METRICS = {
    "roe": True,
    "fcf_margin": True,
    "debt_to_equity": False,
}


def quality_score(df: pd.DataFrame) -> pd.Series:
    available = [c for c in QUALITY_METRICS if c in df.columns]
    if not available:
        warnings.warn(
            "quality_score: no quality metrics (roe, fcf_margin, debt_to_equity) "
            "in universe; returning NaN (excluded from composite).",
            UserWarning,
        )
        return pd.Series(np.nan, index=df.index, name="quality")

    parts = []
    for col in available:
        s = pd.to_numeric(df[col], errors="coerce")
        if not QUALITY_METRICS[col]:
            s = -s  # lower leverage = better
        s = s.groupby(df["sector"]).transform(lambda x: x.fillna(x.median()))
        parts.append(s)
    return pd.concat(parts, axis=1).mean(axis=1).rename("quality")
