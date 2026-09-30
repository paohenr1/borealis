"""Noise factor: the TRUE negative control. Null by construction.

Seeded Gaussian noise, one draw per (date, ticker). Deterministic: the
seed is derived from the date string plus a fixed salt (sha256), so the
same date scored twice gives identical values while different dates give
different draws. Within a date, tickers are drawn in sorted order from a
single per-date generator, so every ticker gets its own independent draw
(the cross-section is never degenerate).

2026-09-30 (sleeve taxonomy): this sleeve replaces growth as the lab's
negative control. Growth is a plausible factor that failed testing -- a
rejected hypothesis, not a control. A control must be null BY
CONSTRUCTION, which noise is: its information coefficient should hover
near zero on every run. If the noise sleeve ever clears |t| > 2, distrust
the lab machinery, not the market.

Weight 0.00 always. It is scored (z_noise appears in output) but never
enters the composite.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

SALT = "borealis-noise-v1"
RAW_COL = "noise_raw"


def _date_seed(seed_key: str) -> int:
    digest = hashlib.sha256(f"{SALT}|{seed_key}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _date_keys(df: pd.DataFrame, seed_key: str | None) -> pd.Series:
    # An explicit seed key (e.g. the live run's as-of date) wins; otherwise
    # fall back to the frame's date column (lab path: many dates per frame).
    if seed_key is not None:
        return pd.Series(seed_key, index=df.index, dtype=str)
    if "date" in df.columns:
        return pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    raise ValueError("noise_score needs a 'date' column or an explicit seed_key")


def noise_score(df: pd.DataFrame, seed_key: str | None = None) -> pd.Series:
    """Seeded N(0,1) draw per row. Higher = nothing; orientation is moot.

    Deterministic per (date, ticker): scoring the same date twice gives
    identical values; different dates give different draws.
    """
    if df.empty:
        return pd.Series(np.nan, index=df.index, dtype=float, name="noise")
    if "ticker" not in df.columns:
        raise ValueError("noise_score needs a 'ticker' column")
    date_keys = _date_keys(df, seed_key)
    tickers = df["ticker"].astype(str)
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for dkey, idx in date_keys.groupby(date_keys, sort=False).groups.items():
        sub = tickers.loc[idx].sort_values(kind="mergesort")
        rng = np.random.default_rng(_date_seed(str(dkey)))
        out.loc[sub.index] = rng.standard_normal(len(sub))
    return out.rename("noise")


def add_noise_raw(frame: pd.DataFrame, date_col: str = "date",
                  ticker_col: str = "ticker") -> pd.DataFrame:
    """Add the ``noise_raw`` column for the lab path (panel frames).

    The lab z-scores it within (date, sector) via add_lab_zscores like any
    other factor column, producing z_noise_raw -> sleeve_noise.
    """
    out = frame.copy()
    ren = {date_col: "date", ticker_col: "ticker"}
    tmp = frame.rename(columns=ren)
    out[RAW_COL] = noise_score(tmp).to_numpy()
    return out
