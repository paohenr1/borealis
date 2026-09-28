"""Value factor: cheap on P/E, P/S, PEG. Higher score = cheaper.

Critical rule: a ratio of zero or negative means missing/negative earnings.
It is quarantined as NaN (then sector-median imputed) — NEVER ranked as
"cheapest".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VALUE_METRICS = ["pe_ratio", "ps_ratio", "peg_ratio"]


def _clean_ratio(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.where(s > 0, np.nan)


def value_score(df: pd.DataFrame) -> pd.Series:
    parts = []
    for col in VALUE_METRICS:
        if col not in df.columns:
            continue
        clean = _clean_ratio(df[col])
        cheapness = 1.0 / clean  # higher = cheaper
        cheapness = cheapness.groupby(df["sector"]).transform(
            lambda x: x.fillna(x.median())
        )
        parts.append(cheapness)
    if not parts:
        return pd.Series(np.nan, index=df.index, name="value")
    return pd.concat(parts, axis=1).mean(axis=1).rename("value")
