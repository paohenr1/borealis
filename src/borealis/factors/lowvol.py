"""Low-vol factor: lower trailing beta preferred. Higher score = calmer."""
from __future__ import annotations

import numpy as np
import pandas as pd


def lowvol_score(df: pd.DataFrame) -> pd.Series:
    s = pd.to_numeric(df["trailing_beta"], errors="coerce")
    s = s.groupby(df["sector"]).transform(lambda x: x.fillna(x.median()))
    return (-s).rename("lowvol")
