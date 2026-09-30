"""Tests for the factor-efficacy lab (synthetic panels only)."""
import numpy as np
import pandas as pd
import pytest

from borealis.lab import halflife, ic, preprocess, quintiles
from borealis.lab.run import month_end_dates


def _frame(rows):
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------- IC math ----------

def test_rank_ic_perfect_positive():
    z = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0] * 10)
    f = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0] * 10)
    assert ic.rank_ic(z, f) == 1.0


def test_rank_ic_perfect_negative():
    z = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0] * 10)
    f = pd.Series([50.0, 40.0, 30.0, 20.0, 10.0] * 10)
    assert ic.rank_ic(z, f) == -1.0


def test_rank_ic_constant_is_nan():
    z = pd.Series([1.0] * 50)
    f = pd.Series(np.arange(50, dtype=float))
    assert np.isnan(ic.rank_ic(z, f))


def test_rank_ic_min_n():
    z = pd.Series([1.0, 2.0, 3.0])
    f = pd.Series([1.0, 2.0, 3.0])
    assert np.isnan(ic.rank_ic(z, f, min_n=30))


def test_ic_summary_values():
    s = pd.Series([0.05, -0.02, 0.03, 0.08, -0.01, 0.04])
    out = ic.ic_summary(s)
    assert out["n"] == 6
    assert out["mean"] == s.mean()
    assert out["tstat"] == s.mean() / (s.std(ddof=1) / np.sqrt(6))
    assert out["hit_rate"] == 4 / 6


def test_ic_summary_too_few():
    out = ic.ic_summary(pd.Series([0.05]))
    assert out["n"] == 1 and np.isnan(out["mean"])


# ---------- quintiles ----------

def test_quintile_spread_known():
    # two return levels -> 1%/99% winsorization is the identity here
    n = 100
    df = _frame([{"date": "2020-01-31", "ticker": f"T{i:03d}",
                  "z_pe": float(i), "ret_fwd_21d": 0.0 if i < 50 else 1.0}
                 for i in range(n)])
    qret = quintiles.quintile_returns(df, "z_pe", "ret_fwd_21d")
    assert len(qret) == 1
    assert qret["spread"].iloc[0] == 1.0  # Q5 all 1.0, Q1 all 0.0
    assert qret["q1"].iloc[0] == 0.0
    assert qret["q5"].iloc[0] == 1.0


def test_quintile_ties_unassignable():
    df = _frame([{"date": "2020-01-31", "ticker": f"T{i:03d}",
                  "z_pe": 1.0, "ret_fwd_21d": float(i)}
                 for i in range(100)])
    qret = quintiles.quintile_returns(df, "z_pe", "ret_fwd_21d")
    assert len(qret) == 0  # constant z -> fewer than 5 bins -> skipped


def test_spread_summary_values():
    qret = pd.DataFrame(
        {"q1": [0.01, 0.02], "q5": [0.05, 0.06], "spread": [0.04, 0.04]},
        index=pd.to_datetime(["2020-01-31", "2020-02-29"]))
    out = quintiles.spread_summary(qret)
    assert out["mean"] == 0.04
    assert out["q1_mean"] == 0.015
    assert out["q5_mean"] == 0.055
    assert out["cumulative"] == 0.08
    assert out["hit_rate"] == 1.0


def test_forward_returns_winsorized_per_date():
    # one lottery ticket (+10000%) must not dominate the quintile mean
    rows = [{"date": "2020-01-31", "ticker": f"T{i:03d}",
             "z": float(i), "ret": 0.01} for i in range(200)]
    rows[199]["ret"] = 100.0  # 10000% outlier in the top quintile
    df = _frame(rows)
    w = quintiles.winsorize_returns(df, "ret")
    assert w.max() < 100.0  # clipped at the 99th percentile
    qret = quintiles.quintile_returns(df, "z", "ret")
    assert qret["q5"].iloc[0] < 1.0  # sane, not ~20% from one ticket


# ---------- half-life ----------

def test_half_life_interpolation():
    decay = {5: 0.9, 21: 0.7, 42: 0.4, 63: 0.2}
    out = halflife.half_life(decay)
    assert out["days"] == 35.0  # 21 + (0.7-0.5)/(0.7-0.4) * 21
    assert out["censored"] is None


def test_half_life_below_at_first_lag():
    out = halflife.half_life({5: 0.3, 21: 0.1})
    assert out["censored"] == "below-threshold-at-first-lag"


def test_half_life_above_at_max_lag():
    out = halflife.half_life({5: 0.9, 21: 0.8})
    assert out["censored"] == "above-0.5-at-max-lag"
    assert out["days"] == 21.0


def test_half_life_no_data():
    out = halflife.half_life({5: np.nan})
    assert out["days"] is None


def test_decay_curve_identical_ranks():
    d0, d1 = pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-07")
    rows = ([{"date": d0, "ticker": f"T{i:02d}", "r": float(i)} for i in range(40)]
            + [{"date": d1, "ticker": f"T{i:02d}", "r": float(i)} for i in range(40)])
    df = pd.DataFrame(rows)
    decay = halflife.decay_curve(df, "r", [d0], [d0, d1], lags=[1])
    assert decay[1] == 1.0


# ---------- preprocessing: orientation, quarantine, unknown sector ----------

def test_orientation_ev_ebitda_cheaper_is_better():
    df = _frame([{"date": "2020-01-31", "ticker": "A", "sector": "tech", "ev_ebitda": 8.0},
                 {"date": "2020-01-31", "ticker": "B", "sector": "tech", "ev_ebitda": 16.0}])
    z = preprocess.zscore_by_date_sector(
        df.assign(oriented_ev_ebitda=preprocess.oriented_factor(df, "ev_ebitda")),
        "oriented_ev_ebitda")
    assert z.iloc[0] > z.iloc[1]  # lower EV/EBITDA -> higher z


def test_quarantine_nonpositive_ev_ebitda():
    df = _frame([{"date": "2020-01-31", "ticker": t, "sector": "tech", "ev_ebitda": v}
                 for t, v in [("A", 10.0), ("B", -5.0), ("C", 0.0), ("D", 20.0)]])
    oriented = preprocess.oriented_factor(df, "ev_ebitda")
    assert oriented.isna().tolist() == [False, True, True, False]


def test_dropped_factors_absent_from_universe():
    for f in preprocess.DROPPED_FACTORS:
        assert f not in preprocess.FACTOR_DIRECTION
    with pytest.raises(KeyError):
        preprocess.oriented_factor(
            _frame([{"date": "2020-01-31", "ticker": "A", "sector": "tech"}]), "pe")


def test_value_sleeve_is_four_metrics():
    # 2026-09-30 sleeve decisions: P/E replaced by earnings yield (same
    # information, better-behaved in the z-score pipeline).
    value_factors = {"earn_yield", "ps", "ev_ebitda", "pb"}
    assert value_factors <= set(preprocess.FACTOR_DIRECTION)
    assert value_factors == set(preprocess.SLEEVES["value"])
    assert not ({"ev_ebit", "ev_fcff"} & set(preprocess.SLEEVES["value"]))
    # pe stays scored individually as a diagnostic
    assert "pe" in preprocess.FACTOR_DIRECTION


def test_lowvol_sleeve_is_realized_vol():
    # 2026-09-30 sleeve decisions: beta_252d rejected on both universes;
    # the live low-vol definition is 126-day realized vol.
    assert preprocess.SLEEVES["lowvol"] == ["vol_126d"]
    assert "beta_252d" in preprocess.FACTOR_DIRECTION  # diagnostic


def test_size_orientation_flipped_regime_dependent():
    # enterprise_value now bets WITH the 2020-2026 mega-cap regime (larger =
    # more attractive); the regime note must stay in the source for the flip-back rule.
    assert preprocess.FACTOR_DIRECTION["enterprise_value"] == 1
    src = open(preprocess.__file__).read()
    assert "REGIME-DEPENDENT" in src and "trailing 12-month" in src


def test_unknown_sector_kept_as_own_bucket():
    df = _frame([
        {"date": "2020-01-31", "ticker": "A", "sector": "tech", "roe": 1.0},
        {"date": "2020-01-31", "ticker": "B", "sector": "tech", "roe": 3.0},
        {"date": "2020-01-31", "ticker": "C", "sector": "unknown", "roe": 10.0},
        {"date": "2020-01-31", "ticker": "D", "sector": "unknown", "roe": 30.0},
    ])
    out = preprocess.add_lab_zscores(df, ["roe"])
    z = out["z_roe"]
    assert z.notna().all()  # no rows dropped, unknown bucket scored
    # within-bucket ordering preserved, each bucket ±0.7071
    assert z.iloc[1] > z.iloc[0]
    assert z.iloc[3] > z.iloc[2]
    assert abs(z.iloc[0] + 0.7071) < 1e-3
    assert abs(z.iloc[2] + 0.7071) < 1e-3


def test_add_lab_zscores_per_date():
    df = _frame([
        {"date": "2020-01-31", "ticker": "A", "sector": "tech", "roe": 1.0},
        {"date": "2020-01-31", "ticker": "B", "sector": "tech", "roe": 3.0},
        {"date": "2020-02-29", "ticker": "A", "sector": "tech", "roe": 5.0},
        {"date": "2020-02-29", "ticker": "B", "sector": "tech", "roe": 1.0},
    ])
    out = preprocess.add_lab_zscores(df, ["roe"])
    jan = out[out["date"] == "2020-01-31"].set_index("ticker")["z_roe"]
    feb = out[out["date"] == "2020-02-29"].set_index("ticker")["z_roe"]
    assert jan["B"] > jan["A"] and feb["A"] > feb["B"]  # scored per date


# ---------- date selection ----------

def test_month_end_dates():
    dates = [pd.Timestamp(d) for d in
             ["2020-01-15", "2020-01-31", "2020-02-15", "2020-02-28"]]
    assert month_end_dates(dates) == [pd.Timestamp("2020-01-31"),
                                      pd.Timestamp("2020-02-28")]


# ---------- end-to-end on synthetic panel: no lookahead by construction ----------

def test_lab_pipeline_direction():
    # factor z at t perfectly predicts forward return -> IC +1, spread > 0
    rows = []
    for m, d in enumerate(["2020-01-31", "2020-02-29", "2020-03-31"]):
        for i in range(60):
            rows.append({"date": d, "ticker": f"T{i:02d}", "sector": "tech",
                         "roe": float(i), "ret_fwd_21d": float(i) / 1000})
    df = _frame(rows)
    df = preprocess.add_lab_zscores(df, ["roe"])
    ics = ic.ic_series(df, "z_roe", "ret_fwd_21d")
    assert (ics > 0.99).all()
    qret = quintiles.quintile_returns(df, "z_roe", "ret_fwd_21d")
    assert (qret["spread"] > 0).all()
