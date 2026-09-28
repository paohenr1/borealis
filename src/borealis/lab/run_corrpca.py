"""Orchestration: factor correlation + PCA over the PIT panel (read-only).

Reuses the efficacy lab's sampling discipline (month-end rebalance dates) and
preprocessing (orientation, quarantine, sector-neutral z-scores). Read-only:
the panel is never modified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from borealis.lab import corrpca, preprocess, report_corrpca
from borealis.lab.run import load_lab_frame, month_end_dates


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


def _priority_from_efficacy(efficacy_json: str | Path | None) -> dict | None:
    """|IC t-stat| per factor from the efficacy lab JSON (keep-best rule)."""
    if not efficacy_json:
        return None
    res = json.loads(Path(efficacy_json).read_text())["results"]
    prio = {}
    for f, r in res.items():
        t = r.get("ic_21", {}).get("tstat")
        if t is not None and not (isinstance(t, float) and np.isnan(t)):
            prio[f] = abs(t)
    return prio or None


def run_corrpca(panel_dir: str | Path, out_dir: str | Path,
                factors: list[str] | None = None,
                max_factors: int | None = None,
                efficacy_json: str | Path | None = None) -> dict:
    panel_dir, out_dir = Path(panel_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset = ds.dataset(str(panel_dir), format="parquet", partitioning="hive")
    all_dates = sorted(t.as_py() for t in
                       dataset.to_table(columns=["date"]).column("date").unique())
    all_dates = [pd.Timestamp(d) for d in all_dates]
    factors = factors or preprocess.available_factors(dataset.schema.names)
    if max_factors:
        factors = factors[:max_factors]
    print(f"[corrpca] {len(all_dates)} panel dates, factors: {factors}",
          flush=True)

    rebal = month_end_dates(all_dates)
    frame = load_lab_frame(panel_dir, rebal, factors, need_returns=False)
    frame = preprocess.add_lab_zscores(frame, factors)
    zcols = [f"z_{f}" for f in factors]
    print(f"[corrpca] frame: {len(frame):,} rows x {len(rebal)} dates",
          flush=True)

    mats = corrpca.date_corr_matrices(frame, zcols)
    print(f"[corrpca] {len(mats)} usable date matrices", flush=True)
    corr = corrpca.average_corr(mats)
    corr.index = factors
    corr.columns = factors
    pairs = corrpca.ranked_pairs(corr)
    pc = corrpca.pca(corr)
    effdim = corrpca.effective_dimensionality(pc)
    priority = _priority_from_efficacy(efficacy_json)
    clusters = corrpca.redundancy_clusters(corr, priority=priority)

    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel": str(panel_dir),
        "n_dates": len(rebal),
        "n_date_matrices": len(mats),
        "date_min": str(min(rebal).date()),
        "date_max": str(max(rebal).date()),
        "efficacy_json": str(efficacy_json) if efficacy_json else None,
        "scheme": [
            "Rebalance dates: month-end trading days in the panel "
            f"({len(rebal)} dates, {min(rebal).date()} to {max(rebal).date()}).",
            "Factors oriented (higher = more attractive), zero/negative value "
            "ratios quarantined, winsorized at ±3σ and z-scored within "
            "(date, sector); 'unknown' sector kept as its own bucket.",
            "Per-date Pearson correlation of z-scores (pairwise complete, "
            "min_periods=200; dates with <200 rows skipped), Fisher-z "
            "averaged back to correlation space; forced symmetric, unit "
            "diagonal.",
            "PCA on the date-averaged correlation matrix (purely "
            "cross-sectional; pooled z-scores would let high-volatility "
            "dates dominate).",
            "Redundancy: greedy clusters at |corr| ≥ 0.70; cluster keeper = "
            "highest |IC t-stat| from the efficacy lab"
            + (" (from " + str(efficacy_json) + ")."
               if efficacy_json else " (no efficacy JSON supplied)."),
        ],
        "caveats": [
            "Contemporaneous factor structure, not prediction: no lookahead "
            "issue exists here by construction (nothing at t is joined to "
            "information from after t).",
            "37% of panel rows have sector 'unknown' (kept as its own "
            "neutralization bucket, not dropped).",
            "Fundamentals cover ~5,880 of 22,569 tickers; small caps are "
            "largely price-only, so factor z-scores are NaN for them and "
            "pairwise-complete correlations lean on covered names.",
            "Restated fundamental vintages embed later revisions (values, "
            "not availability) — inherited from the panel.",
            "Average correlations smooth over regime changes; a single "
            "2020-2026 mean can hide time-varying structure (e.g. the "
            "2022 rate shock).",
        ],
    }
    md = report_corrpca.build_corrpca_report(corr, pairs, pc, effdim,
                                             clusters, meta)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    md_path = out_dir / f"factor_correlation_pca_{stamp}.md"
    md_path.write_text(md)
    payload = {
        "meta": meta,
        "corr": corr.round(4).to_dict(),
        "pairs": pairs.round(4).to_dict(orient="records"),
        "pca": {
            "factors": pc["factors"],
            "eigenvalues": pc["eigenvalues"].tolist(),
            "explained": pc["explained"].tolist(),
            "cumulative": pc["cumulative"].tolist(),
            "loadings": pc["loadings"].round(4).to_dict(),
        },
        "effective_dimensionality": effdim,
        "clusters": clusters,
    }
    json_path = out_dir / f"factor_correlation_pca_{stamp}.json"
    json_path.write_text(json.dumps(payload, default=_jsonable, indent=1))
    print(f"[corrpca] wrote {md_path}\n[corrpca] wrote {json_path}", flush=True)
    return {"report_md": str(md_path), "report_json": str(json_path),
            "corr": corr, "pairs": pairs, "pca": pc,
            "effective_dimensionality": effdim, "clusters": clusters,
            "meta": meta}
