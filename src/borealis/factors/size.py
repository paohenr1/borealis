"""Size factor: log enterprise value. Higher = larger = more attractive.

REGIME-DEPENDENT: the factor lab measured enterprise_value with a positive
orientation (IC +0.0593, t +5.43, 21d) over 2020-2026 because mega caps
outperformed -- the classic small-cap premium was absent. The orientation
was deliberately flipped from the academic default (smaller = better).

Flip-back rule (lab/preprocess.py): if the small-cap premium reappears,
i.e. the trailing-12m size IC turns positive with the academic orientation,
flip this sleeve's direction back to smaller = better. Revisit at least
annually.

Log transform: EV is lognormal across a 500-name universe; raw values
would let the top few mega caps dominate the winsorize/z-score pipeline.
Rank IC (what the lab measured) is invariant to the log, so this does not
contradict the lab evidence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def size_score(df: pd.DataFrame) -> pd.Series:
    s = pd.to_numeric(df["enterprise_value"], errors="coerce")
    s = np.log(s.where(s > 0))  # nonpositive EV -> NaN, then imputed below
    s = s.groupby(df["sector"]).transform(lambda x: x.fillna(x.median()))
    return s.rename("size")
