"""Orchestration: load the PIT panel, run IC / quintile / half-life analyses.

Sampling scheme (stated in the report):
- Rebalance dates: month-end trading days in the panel.
- IC + quintile spreads: per date, sector-neutral z-scored factor at t vs
  forward total return after t (21d primary, 63d secondary). Point-in-time
  safe: z(t) only ever meets ret_fwd(t -> t+h).
- Half-life: semi-annual base dates; rank autocorrelation of the z-score
  ranks at trading-day lags [5, 21, 42, 63, 126, 189, 252].

Read-only: the panel is never modified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from borealis.lab import halflife, ic, preprocess, price_proxies, quintiles, report
from borealis.lab import composite as lab_composite

HORIZONS = {21: "ret_fwd_21d", 63: "ret_fwd_63d"}
HALF_LIFE_LAGS = halflife.DEFAULT_LAGS
MIN_VALID_PER_DATE = 200
PROXY_FACTORS = ["mom_12m1m", "vol_126d", "beta_252d"]


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def month_end_dates(all_dates: list[pd.Timestamp]) -> list[pd.Timestamp]:
    """Last trading day of each calendar month present in the panel."""
    s = pd.Series(sorted(all_dates))
    return sorted(s.groupby([s.dt.year, s.dt.month]).max().tolist())


def load_lab_frame(panel_dir: Path, dates: list[pd.Timestamp],
                   factors: list[str],
                   need_returns: bool = True) -> pd.DataFrame:
    """Read-only pull of the panel for the given dates and columns."""
    cols = ["ticker", "date", "sector"] + factors
    if need_returns:
        cols += list(HORIZONS.values())
    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    table = dataset.to_table(
        columns=[c for c in cols if c in dataset.schema.names],
        filter=ds.field("date").isin([pd.Timestamp(d) for d in dates]),
    )
    df = table.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].astype(str)
    return df


def run_lab(panel_dir: str | Path, out_dir: str | Path,
            factors: list[str] | None = None,
            max_factors: int | None = None,
            prices_path: str | Path | None = None) -> dict:
    panel_dir, out_dir = Path(panel_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    all_dates = sorted(t.as_py() for t in
                       dataset.to_table(columns=["date"]).column("date").unique())
    all_dates = [pd.Timestamp(d) for d in all_dates]
    if factors is None:
        factors = preprocess.available_factors(dataset.schema.names)
        factors = factors + [f for f in PROXY_FACTORS if f not in factors]
    if max_factors:
        factors = factors[:max_factors]
    want_proxies = any(f in PROXY_FACTORS for f in factors)
    if prices_path is None:
        prices_path = panel_dir.parent / "prices_clean.parquet"
    print(f"[lab] {len(all_dates)} panel dates, factors: {factors}", flush=True)

    # ---- date planning (rebalance + half-life needs) ----
    rebal = month_end_dates(all_dates)
    base_dates = rebal[2::6]
    base_dates = [d for d in base_dates
                  if all_dates.index(d) + max(HALF_LIFE_LAGS) < len(all_dates)]
    needed = set(base_dates)
    for bd in base_dates:
        i = all_dates.index(bd)
        needed.update(all_dates[i + lag] for lag in HALF_LIFE_LAGS)

    # ---- price proxies (computed once for all needed dates, read-only) ----
    proxy_frame = None
    if want_proxies:
        proxy_dates = sorted(set(rebal) | set(needed))
        proxy_frame = price_proxies.compute_price_proxies(prices_path,
                                                          proxy_dates)
        print(f"[lab] proxies: {len(proxy_frame):,} rows x "
              f"{len(proxy_dates)} dates", flush=True)

    # ---- IC + quintile spreads on month-end rebalance dates ----
    frame = load_lab_frame(panel_dir, rebal, factors, need_returns=True)
    if proxy_frame is not None:
        frame = frame.merge(proxy_frame, on=["ticker", "date"], how="left")
    frame = preprocess.add_lab_zscores(frame, factors)
    frame["z_composite"] = lab_composite.composite_zscore(frame)
    print(f"[lab] rebalance frame: {len(frame):,} rows x {len(rebal)} dates",
          flush=True)

    # ---- sleeve-level ICs (for the composite weight decision) ----
    sleeve_z = lab_composite.sleeve_zscores(frame)

    results: dict = {}
    lab_factors = factors + ["composite"]
    for f in lab_factors:
        zc = "z_composite" if f == "composite" else f"z_{f}"
        r = results.setdefault(f, {})
        for h, retcol in HORIZONS.items():
            valid = frame.dropna(subset=[zc, retcol])
            counts = valid.groupby("date", observed=True).size()
            ok_dates = counts[counts >= MIN_VALID_PER_DATE].index
            sub = frame[frame["date"].isin(ok_dates)]
            ics = ic.ic_series(sub, zc, retcol)
            r[f"ic_{h}"] = ic.ic_summary(ics)
            qret = quintiles.quintile_returns(sub, zc, retcol)
            r[f"qspread_{h}"] = quintiles.spread_summary(qret)
            r[f"annual_{h}"] = {int(y): float(v)
                                for y, v in quintiles.annual_spreads(qret).items()}
        print(f"[lab] {f}: IC21={r['ic_21']['mean']:+.4f} "
              f"(t={r['ic_21']['tstat']:+.2f}), spread21={r['qspread_21']['mean']:+.2%}, "
              f"HL done below", flush=True)

    sleeve_ics = {}
    for sleeve in lab_composite.SLEEVES:
        zc = f"sleeve_{sleeve}"
        if zc not in sleeve_z.columns:
            continue
        tmp = pd.DataFrame({"date": frame["date"], zc: sleeve_z[zc],
                            "f": frame["ret_fwd_21d"]}).dropna()
        counts = tmp.groupby("date", observed=True).size()
        ok_dates = counts[counts >= MIN_VALID_PER_DATE].index
        ics = ic.ic_series(tmp[tmp["date"].isin(ok_dates)], zc, "f")
        sleeve_ics[sleeve] = ic.ic_summary(ics)

    # ---- half-life on semi-annual base dates ----
    hl_frame = load_lab_frame(panel_dir, sorted(needed), factors,
                              need_returns=False)
    if proxy_frame is not None:
        hl_frame = hl_frame.merge(proxy_frame, on=["ticker", "date"],
                                  how="left")
    hl_frame = preprocess.add_lab_zscores(hl_frame, factors)
    hl_frame["z_composite"] = lab_composite.composite_zscore(hl_frame)
    for f in lab_factors:
        zc = "z_composite" if f == "composite" else f"z_{f}"
        ranks = hl_frame.assign(
            _rank=hl_frame.groupby("date", observed=True)[zc]
            .rank()).rename(columns={"_rank": "rank_tmp"})
        decay = halflife.decay_curve(ranks, "rank_tmp", base_dates, all_dates,
                                     HALF_LIFE_LAGS)
        results[f]["decay"] = decay
        results[f]["half_life"] = halflife.half_life(decay)
        hl = results[f]["half_life"]
        d = hl["days"]
        note = f" ({hl['censored']})" if hl["censored"] else ""
        print(f"[lab] {f}: half-life={f'{d:.0f}d' if d else 'n/a'}{note}",
              flush=True)

    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel": str(panel_dir),
        "n_dates": len(rebal),
        "date_min": str(min(rebal).date()),
        "date_max": str(max(rebal).date()),
        "lags": HALF_LIFE_LAGS,
        "scheme": [
            "Rebalance dates: month-end trading days in the panel "
            f"({len(rebal)} dates, {min(rebal).date()} to {max(rebal).date()}).",
            "Factors oriented (higher = more attractive), zero/negative value "
            "ratios quarantined, winsorized at ±3σ and z-scored within "
            "(date, sector); 'unknown' sector kept as its own bucket.",
            "IC: Spearman rank correlation of z(t) vs forward total return "
            "after t; 21-trading-day primary, 63-day secondary.",
            "Quintiles: per-date sort on z into 5 equal groups; spread = "
            "equal-weighted Q5 − Q1 forward return, with forward returns "
            "winsorized per date at the 1st/99th percentiles (micro-cap "
            "lottery tickets would otherwise dominate equal-weighted "
            "means).",
            f"Half-life: semi-annual base dates ({len(base_dates)}), rank "
            f"autocorrelation of z-score ranks at trading-day lags "
            f"{HALF_LIFE_LAGS}; first crossing of 0.5, interpolated.",
            "Point-in-time discipline inherited from the panel; z(t) only "
            "meets returns after t.",
            "Price proxies (mom_12m1m, vol_126d) built from daily "
            "split/dividend-adjusted closes: momentum = 12-month trailing "
            "total return skipping the most recent month "
            "(adj_close(t-21)/adj_close(t-252)-1); volatility = 126-day "
            "annualized std of daily total returns. Full price universe; "
            "no lookahead (latest input at t-21 for momentum).",
            "Composite = sleeve-weighted mean of sleeve z-scores "
            f"(weights {lab_composite.SLEEVE_WEIGHTS}), renormalized per "
            "ticker across sleeves present.",
        ],
        "caveats": [
            "37% of panel rows have sector 'unknown' (kept as its own "
            "neutralization bucket, not dropped).",
            "Fundamentals cover ~5,880 of 22,569 tickers; small caps are "
            "largely price-only, so factor z-scores are NaN for them.",
            "Restated fundamental vintages embed later revisions (values, "
            "not availability).",
            "Panel returns are total returns (split/dividend-adjusted); "
            "dividends are not modeled separately.",
            "Forward-return horizons truncate the sample end (63d IC uses "
            "fewer recent dates).",
        ],
    }
    md = report.build_report(results, meta)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    md_path = out_dir / f"factor_efficacy_{stamp}.md"
    md_path.write_text(md)
    json_path = out_dir / f"factor_efficacy_{stamp}.json"
    json_path.write_text(json.dumps({"meta": meta, "results": results,
                                     "sleeve_ics": sleeve_ics},
                                    default=_jsonable, indent=1))
    print(f"[lab] wrote {md_path}\n[lab] wrote {json_path}", flush=True)
    return {"report_md": str(md_path), "report_json": str(json_path),
            "results": results, "meta": meta, "sleeve_ics": sleeve_ics}
