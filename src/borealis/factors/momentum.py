"""Momentum factor: distance from 52-week low. Higher = stronger trend.

Placeholder until trailing 6/12m returns are added to the feed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def momentum_score(df: pd.DataFrame) -> pd.Series:
    s = pd.to_numeric(df["pct_above_52w_low"], errors="coerce")
    s = s.groupby(df["sector"]).transform(lambda x: x.fillna(x.median()))
    return s.rename("momentum")
