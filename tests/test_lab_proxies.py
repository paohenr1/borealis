"""Tests for price-derived proxies, sleeve map, and lab composite (synthetic data)."""
import numpy as np
import pandas as pd
import pytest

from borealis.lab import composite as lab_composite
from borealis.lab import price_proxies
from borealis.lab.preprocess import FACTOR_DIRECTION, SLEEVES


def _prices(rows_per_ticker):
    """rows_per_ticker: {ticker: list of adj_close}. Business-day dates."""
    rows = []
    for t, pxs in rows_per_ticker.items():
        dates = pd.bdate_range("2020-01-01", periods=len(pxs))
        for d, p in zip(dates, pxs):
            rows.append({"ticker": t, "date": d, "adj_close": float(p)})
    df = pd.DataFrame(rows)
    return df


def _write_prices(df, tmp_path):
    p = tmp_path / "prices_clean.parquet"
    df.to_parquet(p)
    return p


def _proxies(df, tmp_path, at="last"):
    p = _write_prices(df, tmp_path)
    dates = sorted(df["date"].unique())
    t = dates[-1] if at == "last" else at
    return price_proxies.compute_price_proxies(p, [t])


# ---------- momentum construction ----------

def test_mom_flat_price_is_zero(tmp_path):
    df = _prices({"A": [100.0] * 300})
    out = _proxies(df, tmp_path)
    assert out["mom_12m1m"].iloc[0] == pytest.approx(0.0)


def test_mom_doubling_is_one(tmp_path):
    # 50 -> 100 between t-252 and t-21  =>  +100%
    pxs = [50.0] * 48 + [100.0] * 252
    df = _prices({"A": pxs})
    out = _proxies(df, tmp_path)
    assert out["mom_12m1m"].iloc[0] == pytest.approx(1.0)


def test_mom_skips_most_recent_month(tmp_path):
    # double happens entirely within the last 21 trading days -> excluded
    pxs = [100.0] * 279 + [200.0] * 21
    df = _prices({"A": pxs})
    out = _proxies(df, tmp_path)
    assert out["mom_12m1m"].iloc[0] == pytest.approx(0.0)


def test_mom_insufficient_history_is_nan(tmp_path):
    df = _prices({"A": [100.0] * 100})
    out = _proxies(df, tmp_path)
    assert np.isnan(out["mom_12m1m"].iloc[0])


# ---------- volatility construction ----------

def test_vol_flat_price_is_zero(tmp_path):
    df = _prices({"A": [100.0] * 200})
    out = _proxies(df, tmp_path)
    assert out["vol_126d"].iloc[0] == pytest.approx(0.0)


def test_vol_alternating_returns(tmp_path):
    pxs = [100.0]
    for _ in range(199):
        pxs.append(pxs[-1] * (1.01 if len(pxs) % 2 == 1 else 1 / 1.01))
    df = _prices({"A": pxs})
    out = _proxies(df, tmp_path)
    rets = np.array([0.01, -1 / 101.0] * 63)  # 126 daily returns
    expected = rets.std(ddof=1) * np.sqrt(252)
    assert out["vol_126d"].iloc[0] == pytest.approx(expected, rel=1e-9)


def test_vol_insufficient_history_is_nan(tmp_path):
    df = _prices({"A": [100.0] * 50})
    out = _proxies(df, tmp_path)
    assert np.isnan(out["vol_126d"].iloc[0])


# ---------- no lookahead ----------

def test_proxies_ignore_prices_after_t(tmp_path):
    base = [100.0] * 300
    df = _prices({"A": base})
    p = _write_prices(df, tmp_path)
    t0 = sorted(df["date"].unique())[-1]
    before = price_proxies.compute_price_proxies(p, [t0])

    spiked = base + [1000.0] * 30  # 10x spike strictly after t0
    df2 = _prices({"A": spiked})
    p2 = _write_prices(df2, tmp_path)
    after = price_proxies.compute_price_proxies(p2, [t0])

    pd.testing.assert_frame_equal(before, after)


# ---------- orientations & sleeve map ----------

def test_proxy_orientations():
    assert FACTOR_DIRECTION["mom_12m1m"] == 1   # winners keep winning
    assert FACTOR_DIRECTION["vol_126d"] == -1   # calmer is more attractive


def test_div_yield_has_standalone_sleeve():
    assert "div_yield" in SLEEVES["yield"]
    assert "div_yield" not in SLEEVES["value"]
    assert len(SLEEVES["yield"]) == 1


def test_sleeve_members_all_have_directions():
    for sleeve, members in SLEEVES.items():
        for m in members:
            assert m in FACTOR_DIRECTION, f"{m} in sleeve {sleeve} has no direction"


def test_expected_sleeves_present():
    for s in ("value", "quality", "growth", "yield", "momentum",
              "lowvol", "size"):
        assert s in SLEEVES, f"sleeve {s} missing"


# ---------- composite ----------

def test_sleeve_weights_sum_to_one():
    assert sum(lab_composite.SLEEVE_WEIGHTS.values()) == pytest.approx(1.0)


def test_composite_zscore_weighted_mean():
    frame = pd.DataFrame({"z_a": [1.0, 2.0], "z_b": [3.0, 4.0]})
    out = lab_composite.composite_zscore(
        frame, sleeves={"s1": ["a", "b"]}, weights={"s1": 1.0})
    assert out.tolist() == pytest.approx([2.0, 3.0])


def test_composite_renormalizes_over_present_sleeves():
    frame = pd.DataFrame({"z_a": [2.0], "z_b": [np.nan]})
    out = lab_composite.composite_zscore(
        frame,
        sleeves={"s1": ["a"], "s2": ["b"]},
        weights={"s1": 0.6, "s2": 0.4},
    )
    # s2 absent for this ticker -> full weight falls back on s1
    assert out.iloc[0] == pytest.approx(2.0)


def test_composite_all_missing_is_nan():
    frame = pd.DataFrame({"z_a": [np.nan]})
    out = lab_composite.composite_zscore(
        frame, sleeves={"s1": ["a"]}, weights={"s1": 1.0})
    assert np.isnan(out.iloc[0])


def test_composite_unknown_sleeve_weight_raises():
    frame = pd.DataFrame({"z_a": [1.0]})
    with pytest.raises(KeyError):
        lab_composite.composite_zscore(
            frame, sleeves={"s1": ["a"]}, weights={"nope": 1.0})


def test_sleeve_zscores_pairwise_complete():
    frame = pd.DataFrame({"z_a": [1.0, np.nan], "z_b": [3.0, 5.0]})
    out = lab_composite.sleeve_zscores(frame, sleeves={"s1": ["a", "b"]})
    assert out["sleeve_s1"].tolist() == pytest.approx([2.0, 5.0])
