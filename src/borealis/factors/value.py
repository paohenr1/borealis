"""Value factor: cheap on earnings yield, P/S, EV/EBITDA, P/B.
Higher score = cheaper.

2026-09-30: P/E replaced by earnings yield (EY = 1/P/E). Same economic
information, but P/E explodes for near-zero earnings (a $0.01 EPS reads
as a P/E of 2000), which poisons the winsorize/z-score pipeline;
earnings yield is bounded and well-behaved. pe_ratio stays in the frame
as a diagnostic (and the lab still scores pe individually) but is no
longer a sleeve member. In plain English the sleeve is still described
as "P/E (as earnings yield)" -- the academic factor literature's
standard value definition.

PEG was removed 2026-09-29: no vendor tag exists in the Intrinio data
(all-NaN on the live path), and the factor lab's value result was earned
without it. EV/EBITDA and P/B added 2026-09-29.

Metric orientation: earnings yield is already higher=cheaper; the other
three ratios are inverted (1/x) so higher = cheaper for every part.

Critical rule: a ratio of zero or negative means missing/negative earnings.
It is quarantined as NaN (then sector-median imputed) -- NEVER ranked as
"cheapest". Earnings yield is deliberately NOT quarantined: a negative
earnings yield is informative (unlike a negative P/E ratio), which is why
it beats P/E as a value signal. A zero/NaN earnings yield (from pe == 0)
is still NaN, never ranked.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Sleeve members. earn_yield is preferred; on the workbook path (no EY
# column) it is derived as 1/pe_ratio with the same nonpositive
# quarantine, so the workbook sleeve keeps its P/E information in the
# better-behaved form.
VALUE_METRICS = ["earn_yield", "ps_ratio", "ev_to_ebitda", "pb_ratio"]
HIGHER_IS_CHEAPER = {"earn_yield"}


def _clean_ratio(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.where(s > 0, np.nan)


def value_score(df: pd.DataFrame) -> pd.Series:
    cols = set(df.columns)
    parts = []
    for col in VALUE_METRICS:
        if col == "earn_yield" and "earn_yield" not in cols:
            # workbook path: derive EY from P/E (quarantine nonpositive)
            if "pe_ratio" not in cols:
                continue
            ey = 1.0 / _clean_ratio(df["pe_ratio"])
            ey = ey.groupby(df["sector"]).transform(
                lambda x: x.fillna(x.median()))
            parts.append(ey)
            continue
        if col not in cols:
            continue
        if col in HIGHER_IS_CHEAPER:
            cheapness = pd.to_numeric(df[col], errors="coerce")
        else:
            clean = _clean_ratio(df[col])
            cheapness = 1.0 / clean  # higher = cheaper
        cheapness = cheapness.groupby(df["sector"]).transform(
            lambda x: x.fillna(x.median())
        )
        parts.append(cheapness)
    if not parts:
        return pd.Series(np.nan, index=df.index, name="value")
    return pd.concat(parts, axis=1).mean(axis=1).rename("value")
