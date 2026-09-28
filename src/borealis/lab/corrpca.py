"""Factor correlation + PCA on contemporaneous factor structure.

No lookahead concern: this analysis is contemporaneous, not predictive. It
describes how sector-neutral factor z-scores co-move cross-sectionally at
time t. No factor value at t is ever joined to information from after t, so
point-in-time discipline is vacuous here — stated explicitly.

Pipeline per date: Pearson correlation of the z-scored factors (pairwise
complete observations, min_periods guard), then Fisher-z averaging across
dates back to correlation space. Fisher-z averaging is the standard way to
average correlations: it respects the [-1, 1] bounds and down-weights the
skew that raw averaging introduces near the bounds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_VALID_PER_DATE = 200
MIN_PERIODS = 200
REDUNDANCY_THRESHOLD = 0.70


def date_corr_matrices(frame: pd.DataFrame, zcols: list[str],
                       min_periods: int = MIN_PERIODS,
                       method: str = "pearson") -> list[pd.DataFrame]:
    """One correlation matrix per date (pairwise complete).

    ``method`` is passed to ``DataFrame.corr`` ("pearson" or "spearman";
    spearman = rank correlation, robust to the heavy tails in z-scores).
    """
    mats = []
    for _d, g in frame.groupby("date", observed=True):
        if len(g) < MIN_VALID_PER_DATE:
            continue
        m = g[zcols].corr(method=method, min_periods=min_periods)
        if m.notna().any().any():
            mats.append(m)
    return mats


def average_corr(mats: list[pd.DataFrame]) -> pd.DataFrame:
    """Fisher-z mean of per-date correlation matrices, back-transformed.

    Result is forced symmetric with an exact unit diagonal.
    """
    if not mats:
        raise ValueError("no correlation matrices to average")
    cols = mats[0].columns
    arr = np.stack([m.reindex(index=cols, columns=cols).values
                    for m in mats]).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.arctanh(np.clip(arr, -0.9999999, 0.9999999))
    mean_z = np.nanmean(z, axis=0)
    out = np.tanh(mean_z)
    out = (out + out.T) / 2.0
    np.fill_diagonal(out, 1.0)
    return pd.DataFrame(out, index=cols, columns=cols)


def ranked_pairs(corr: pd.DataFrame) -> pd.DataFrame:
    """All unique factor pairs ranked by |correlation| descending."""
    rows = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            rows.append({"factor_a": cols[i], "factor_b": cols[j],
                         "corr": float(corr.iloc[i, j])})
    df = pd.DataFrame(rows)
    df["abs_corr"] = df["corr"].abs()
    return df.sort_values("abs_corr", ascending=False).reset_index(drop=True)


def pca(corr: pd.DataFrame) -> dict:
    """Eigendecomposition of a correlation matrix.

    Returns eigenvalues (desc), explained variance, cumulative variance,
    loadings (eigenvector * sqrt(eigenvalue)) and the orthonormal vectors.
    PCA is run on the date-averaged correlation matrix rather than pooled
    z-scores: that keeps the analysis purely cross-sectional, matching the
    lab's per-date discipline, instead of letting high-volatility dates
    dominate a pooled covariance.
    """
    vals, vecs = np.linalg.eigh(corr.values.astype(float))
    order = np.argsort(vals)[::-1]
    vals = np.clip(vals[order], 0.0, None)
    vecs = vecs[:, order]
    total = vals.sum()
    explained = vals / total if total > 0 else np.zeros_like(vals)
    loadings = vecs * np.sqrt(vals)
    return {
        "factors": list(corr.columns),
        "eigenvalues": vals,
        "explained": explained,
        "cumulative": np.cumsum(explained),
        "loadings": pd.DataFrame(loadings, index=corr.columns,
                                 columns=[f"PC{i+1}" for i in range(len(vals))]),
        "vectors": vecs,
    }


def effective_dimensionality(pca_res: dict,
                             var_thresholds: tuple[float, ...] = (0.8, 0.9)
                             ) -> dict:
    """Kaiser rule (eigenvalue > 1) + number of PCs for 80/90% variance."""
    vals = pca_res["eigenvalues"]
    cum = pca_res["cumulative"]
    return {
        "kaiser_gt1": int((vals > 1.0).sum()),
        **{f"n_pc_{int(t*100)}pct": int(np.searchsorted(cum, t) + 1)
           for t in var_thresholds},
    }


def redundancy_clusters(corr: pd.DataFrame,
                        threshold: float = REDUNDANCY_THRESHOLD,
                        priority: dict[str, float] | None = None
                        ) -> list[dict]:
    """Greedy clusters of factors with |corr| >= threshold (union-find).

    Within each cluster the recommended keeper is the factor with the
    highest ``priority`` score (e.g. |IC t-stat| from the efficacy lab);
    without priorities the first factor alphabetically is kept.
    """
    cols = list(corr.columns)
    parent = {c: c for c in cols}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    pairs = ranked_pairs(corr)
    for _, r in pairs[pairs["abs_corr"] >= threshold].iterrows():
        union(r["factor_a"], r["factor_b"])

    groups: dict[str, list[str]] = {}
    for c in cols:
        groups.setdefault(find(c), []).append(c)
    clusters = []
    for members in groups.values():
        if len(members) < 2:
            continue
        if priority:
            keeper = max(members, key=lambda m: (priority.get(m, 0.0), m))
        else:
            keeper = sorted(members)[0]
        sub = corr.loc[members, members]
        mask = np.triu(np.ones(sub.shape, bool), k=1)
        max_abs = float(sub.abs().where(mask).max().max())
        clusters.append({"members": sorted(members), "keep": keeper,
                         "drop": sorted(set(members) - {keeper}),
                         "max_abs_corr": max_abs})
    return sorted(clusters, key=lambda c: c["max_abs_corr"], reverse=True)
