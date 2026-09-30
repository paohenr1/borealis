"""Growth factor: TTM growth rates (lab definitions). Higher = better.

Prefers the lab's TTM growth set -- revenue, EBIT and EBITDA growth --
when the live feed carries them. Falls back to the quarterly
sales/eps growth columns on the workbook path, which has no TTM feed.

ZERO-WEIGHT FALSIFIED BELIEF (since 2026-09-30): growth is widely believed
to drive equity returns, which is exactly why its failure is worth
keeping visible. The lab measured all three TTM growth rates as weak
(rev_growth IC -0.0017, ebitda_growth t +0.90, ebit_growth t +1.59 --
none near significance). The sleeve is scored every run for transparency
-- the lab reports its failures, not just its successes -- but it is NOT
a candidate: there is no reinstatement rule, and re-promotion would
require a new documented research decision. (It was briefly labeled a
"negative control"; that was wrong -- a control must be null by
construction. Seeded noise in factors/noise.py is the true control.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# The lab's TTM growth definitions (lab/preprocess.py FACTOR_DIRECTION).
TTM_GROWTH_METRICS = ["rev_growth", "ebit_growth", "ebitda_growth"]
# Workbook fallback: quarterly YoY rates from the workbook pipeline.
QTR_GROWTH_METRICS = ["sales_growth_q", "eps_growth_q"]


def growth_score(df: pd.DataFrame) -> pd.Series:
    available = [c for c in TTM_GROWTH_METRICS if c in df.columns
                 and df[c].notna().any()]
    if not available:
        available = [c for c in QTR_GROWTH_METRICS if c in df.columns
                     and df[c].notna().any()]
    if not available:
        return pd.Series(np.nan, index=df.index, name="growth")
    parts = []
    for col in available:
        s = pd.to_numeric(df[col], errors="coerce")
        s = s.groupby(df["sector"]).transform(lambda x: x.fillna(x.median()))
        parts.append(s)
    return pd.concat(parts, axis=1).mean(axis=1).rename("growth")
