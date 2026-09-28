"""Growth factor: trailing quarterly sales growth. Higher = better."""
from __future__ import annotations

import numpy as np
import pandas as pd


def growth_score(df: pd.DataFrame) -> pd.Series:
    s = pd.to_numeric(df["sales_growth_q"], errors="coerce")
    s = s.groupby(df["sector"]).transform(lambda x: x.fillna(x.median()))
    return s.rename("growth")
