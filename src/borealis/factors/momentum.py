"""Momentum factor: 12-1 trailing return (skip most recent month). Higher = stronger trend.

Uses ``mom_12_1`` from the live universe (split/dividend-adjusted closes,
bad-tick quarantined, computed from the same price load as the beta
fallback). Falls back to the ``pct_above_52w_low`` proxy when the column
is absent -- e.g. the workbook path, which has no price history.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def momentum_score(df: pd.DataFrame) -> pd.Series:
    if "mom_12_1" in df.columns and df["mom_12_1"].notna().any():
        s = pd.to_numeric(df["mom_12_1"], errors="coerce")
    else:
        s = pd.to_numeric(df["pct_above_52w_low"], errors="coerce")
    s = s.groupby(df["sector"]).transform(lambda x: x.fillna(x.median()))
    return s.rename("momentum")
