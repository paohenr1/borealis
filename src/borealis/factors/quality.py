"""Quality factor: profitable, cash-generative, conservatively financed.

Higher = better. Metrics are averaged as sleeve parts (sector-median
imputation for missing values), then the composite z-scores the sleeve
within sector. Expanded 2026-09-29 from 3 to 7 metrics on the Intrinio
live path; the workbook path still supplies only roe/fcf_margin/
debt_to_equity and degrades gracefully on the rest.

Known wart: parts are averaged raw, so larger-scale metrics (gross_margin
in percent) weigh more than small-scale ones (fcf_margin as a decimal).
Kept as-is to preserve comparability with the factor lab evidence
(+15.2%/yr, Sharpe 1.29); normalizing within-sleeve would change the
sleeve the lab measured.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

# metric -> higher_better?
QUALITY_METRICS = {
    "roe": True,
    "roa": True,
    "gross_margin": True,
    "profit_margin": True,
    "fcf_margin": True,
    "debt_to_equity": False,
    "debt_to_ebitda": False,
    "interest_coverage": True,  # financial health: EBIT / interest expense
}


def quality_score(df: pd.DataFrame) -> pd.Series:
    available = [c for c in QUALITY_METRICS if c in df.columns]
    if not available:
        warnings.warn(
            "quality_score: no quality metrics "
            f"({', '.join(QUALITY_METRICS)}) in universe; returning NaN "
            "(excluded from composite).",
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
