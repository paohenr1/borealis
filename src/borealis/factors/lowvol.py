"""Low-vol factor: lower realized volatility preferred. Higher score = calmer.

2026-09-30 (sleeve decision): the live definition reverted to 126-day
realized volatility. The 252-day beta-vs-SPY definition was rejected on
both universes (broad -9.35%/yr, large-cap -7.8%/yr -- and worst exactly
in down/high-vol months, when low-vol should protect). trailing_beta
stays in the frame as a diagnostic but is no longer the sleeve.

Column preference: vol_126d (live path, derived from adjusted closes in
ingest/universe_live.py); the workbook path has no price history, so it
falls back to trailing_beta with the same lower-is-better orientation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VOL_COL = "vol_126d"
BETA_FALLBACK_COL = "trailing_beta"


def lowvol_score(df: pd.DataFrame) -> pd.Series:
    col = VOL_COL if VOL_COL in df.columns else BETA_FALLBACK_COL
    s = pd.to_numeric(df[col], errors="coerce")
    s = s.groupby(df["sector"]).transform(lambda x: x.fillna(x.median()))
    return (-s).rename("lowvol")
