"""Tests for factor correlation + PCA (synthetic data only)."""
import unittest

import numpy as np
import pandas as pd

from borealis.lab import corrpca


def _synth_frame(n_dates=4, n_rows=600, seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_dates):
        date = pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(d)
        a = rng.normal(size=n_rows)
        # b is a near-duplicate of a; c is independent
        b = a * 0.95 + rng.normal(scale=0.31, size=n_rows)
        c = rng.normal(size=n_rows)
        for i in range(n_rows):
            rows.append({"date": date, "z_a": a[i], "z_b": b[i], "z_c": c[i]})
    return pd.DataFrame(rows)


# ---------- correlation ----------

def test_corr_symmetric_unit_diagonal():
    frame = _synth_frame()
    mats = corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"])
    assert len(mats) == 4
    avg = corrpca.average_corr(mats)
    assert np.allclose(avg.values, avg.values.T, atol=1e-12)
    assert np.allclose(np.diag(avg.values), 1.0, atol=1e-12)


def test_corr_detects_near_duplicate():
    frame = _synth_frame()
    mats = corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"])
    avg = corrpca.average_corr(mats)
    assert avg.loc["z_a", "z_b"] > 0.9
    assert abs(avg.loc["z_a", "z_c"]) < 0.15


def test_ranked_pairs_sorted():
    frame = _synth_frame()
    avg = corrpca.average_corr(
        corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"]))
    pairs = corrpca.ranked_pairs(avg)
    assert len(pairs) == 3  # C(3,2)
    assert pairs["abs_corr"].is_monotonic_decreasing
    assert pairs.iloc[0]["factor_a"] == "z_a"
    assert pairs.iloc[0]["factor_b"] == "z_b"


def test_sparse_dates_skipped():
    frame = _synth_frame(n_rows=50)  # below MIN_VALID_PER_DATE
    mats = corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"])
    assert mats == []


# ---------- PCA ----------

def test_pca_explained_sums_to_one():
    frame = _synth_frame()
    avg = corrpca.average_corr(
        corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"]))
    pc = corrpca.pca(avg)
    assert abs(pc["explained"].sum() - 1.0) < 1e-10
    assert pc["cumulative"][-1] <= 1.0 + 1e-10
    assert (np.diff(pc["eigenvalues"]) <= 1e-10).all()  # descending


def test_pca_components_orthonormal():
    frame = _synth_frame()
    avg = corrpca.average_corr(
        corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"]))
    pc = corrpca.pca(avg)
    v = pc["vectors"]
    assert np.allclose(v.T @ v, np.eye(v.shape[1]), atol=1e-10)


def test_pca_first_pc_captures_duplicate_axis():
    frame = _synth_frame()
    avg = corrpca.average_corr(
        corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"]))
    pc = corrpca.pca(avg)
    # a and b share one axis -> PC1 should explain well over half
    assert pc["explained"][0] > 0.5
    eff = corrpca.effective_dimensionality(pc)
    assert eff["kaiser_gt1"] >= 1
    assert 1 <= eff["n_pc_80pct"] <= 3


# ---------- redundancy ----------

def test_redundancy_clusters_near_duplicates():
    frame = _synth_frame()
    avg = corrpca.average_corr(
        corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"]))
    clusters = corrpca.redundancy_clusters(avg, threshold=0.70)
    assert len(clusters) == 1
    assert set(clusters[0]["members"]) == {"z_a", "z_b"}
    assert clusters[0]["max_abs_corr"] > 0.9


def test_redundancy_keeper_uses_priority():
    frame = _synth_frame()
    avg = corrpca.average_corr(
        corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"]))
    clusters = corrpca.redundancy_clusters(
        avg, threshold=0.70, priority={"z_a": 1.0, "z_b": 9.0})
    assert clusters[0]["keep"] == "z_b"
    assert clusters[0]["drop"] == ["z_a"]


def test_redundancy_none_below_threshold():
    rng = np.random.default_rng(3)
    cols = [f"z_{i}" for i in range(5)]
    data = {c: rng.normal(size=500) for c in cols}
    df = pd.DataFrame(data)
    df["date"] = pd.Timestamp("2021-01-31")
    avg = corrpca.average_corr(corrpca.date_corr_matrices(df, cols))
    assert corrpca.redundancy_clusters(avg, threshold=0.70) == []


# ---------- rank correlation (method="spearman") ----------

class TestRankCorrelation(unittest.TestCase):
    def test_spearman_matches_pandas_rank_corr(self):
        frame = _synth_frame()
        mats = corrpca.date_corr_matrices(frame, ["z_a", "z_b", "z_c"],
                                          method="spearman")
        assert len(mats) == 4
        # spot-check one date against a direct pandas computation
        g = frame[frame["date"] == frame["date"].iloc[0]]
        expect = g[["z_a", "z_b", "z_c"]].corr(
            method="spearman", min_periods=corrpca.MIN_PERIODS)
        assert np.allclose(mats[0].values, expect.values, atol=1e-12)
        avg = corrpca.average_corr(mats)
        assert avg.loc["z_a", "z_b"] > 0.9  # near-duplicate survives ranking
