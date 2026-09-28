"""Point-in-time panel: (date, ticker) rows with sector, factor inputs, returns.

For every trading date and ticker, fundamentals attached are the latest
vintage with ``available_date <= date`` (``merge_asof``, backward) -- i.e.
only data that was public by that date. ``available_date`` is the later of
``filing_date`` / ``first_calculable_at`` (see ``intrinio_bulk``).

Documented assumptions / caveats:

* ``ADJ_CLOSE`` is split- AND dividend-adjusted (total-return basis), so all
  returns computed here are total returns with dividends embedded; dividends
  are NOT modeled as separate cash flows.
* Restated fundamental vintages are included with their republication date
  as ``available_date``. Availability is point-in-time correct, but values
  embed future revisions (mild lookahead on values, none on availability).
* Delisted securities are kept (their series simply ends) -- no
  survivorship filter is applied.
* Returns use trading-day offsets (21 ~= 1 month).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

# calculation column -> panel column
FACTOR_RENAME = {
    "pricetoearnings": "pe",
    "pricetobook": "pb",
    "pricetorevenue": "ps",
    "evtoebitda": "ev_ebitda",
    "evtoebit": "ev_ebit",
    "evtofcff": "ev_fcff",
    "evtosales": "ev_sales",
    "marketcap": "market_cap",
    "enterprisevalue": "enterprise_value",
    "freecashflow": "fcf",
    "dividendyield": "div_yield",
    "earningsyield": "earn_yield",
    "revenuegrowth": "rev_growth",
    "ebitdagrowth": "ebitda_growth",
    "ebitgrowth": "ebit_growth",
    "bookvaluepershare": "bvps",
    "debttoebitda": "debt_ebitda",
    "roe": "roe",
    "roa": "roa",
    "grossmargin": "gross_margin",
    "operatingmargin": "op_margin",
    "ebitdamargin": "ebitda_margin",
    "profitmargin": "profit_margin",
    "currentratio": "current_ratio",
    "assetturnover": "asset_turnover",
    "leverageratio": "leverage",
}

FUND_META = {
    "available_date": "fund_available_date",
    "end_date": "fund_end_date",
    "fiscal_period": "fund_period",
    "fiscal_year": "fund_fy",
}

# when two vintages share an available_date, prefer the more complete period
_PERIOD_RANK = {"Q1TTM": 1, "Q2TTM": 2, "Q3TTM": 3, "FY": 4}


def _prep_fundamentals(calcs: pd.DataFrame) -> pd.DataFrame:
    fu = calcs.copy()
    fu["ticker"] = fu["ticker"].astype(str)
    fu["available_date"] = pd.to_datetime(fu["available_date"])
    fu["_prank"] = fu["fiscal_period"].map(_PERIOD_RANK).fillna(0).astype(int)
    for c in FACTOR_RENAME:
        if c in fu.columns:
            fu[c] = pd.to_numeric(fu[c], errors="coerce")
    # within (ticker, available_date) prefer the more complete period (FY last);
    # then stable-sort by available_date for merge_asof's global sort requirement
    fu = fu.sort_values(["ticker", "available_date", "_prank"])
    fu = fu.sort_values("available_date", kind="stable")
    keep = ["ticker", "available_date"]
    keep += [c for c in FACTOR_RENAME if c in fu.columns]
    keep += [c for c in FUND_META if c in fu.columns and c != "available_date"]
    return fu[keep]


def _add_returns(px: pd.DataFrame) -> pd.DataFrame:
    px = px.sort_values(["ticker", "date"])
    g = px.groupby("ticker", sort=False)["adj_close"]
    px["ret_21d"] = g.transform(lambda s: s / s.shift(21) - 1)
    px["ret_126d"] = g.transform(lambda s: s / s.shift(126) - 1)
    px["ret_252d"] = g.transform(lambda s: s / s.shift(252) - 1)
    px["ret_fwd_21d"] = g.transform(lambda s: s.shift(-21) / s - 1)
    px["ret_fwd_63d"] = g.transform(lambda s: s.shift(-63) / s - 1)
    return px


def build_panel(prices_path: Path | str, calcs_path: Path | str,
                companies: pd.DataFrame, out_dir: Path | str,
                ticker_batch: int = 2500) -> dict:
    """Build the PIT panel, writing partitioned Parquet. Returns a report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"batches": 0, "rows": 0, "tickers": 0,
                    "date_min": None, "date_max": None}

    prices_ds = ds.dataset(prices_path, format="parquet")
    calcs_ds = ds.dataset(calcs_path, format="parquet")
    tickers = sorted(
        t.as_py() for t in
        prices_ds.to_table(columns=["ticker"]).column("ticker").unique()
        if t.as_py())
    report["tickers"] = len(tickers)

    sector_map = companies.drop_duplicates("company_id").set_index(
        "company_id")["sector"]

    # Expected fundamental columns (RAW calcs names; the rename to panel names
    # happens after the merge) so a batch with zero matching vintages still
    # writes a schema-compatible frame.
    _calc_names = set(calcs_ds.schema.names)
    _fund_factor_cols = [c for c in FACTOR_RENAME if c in _calc_names]
    _fund_meta_cols = [c for c in FUND_META
                       if c in _calc_names and c != "available_date"]

    def _empty_fund_frame(px: pd.DataFrame) -> pd.DataFrame:
        panel = px.copy()
        panel["available_date"] = pd.to_datetime(
            pd.Series(pd.NaT, index=panel.index))
        for c in _fund_factor_cols + _fund_meta_cols:
            panel[c] = np.nan
        return panel

    for b, i in enumerate(range(0, len(tickers), ticker_batch)):
        batch = tickers[i:i + ticker_batch]
        filt = ds.field("ticker").isin(batch)
        px = prices_ds.to_table(filter=filt).to_pandas()
        if not len(px):
            continue
        px["ticker"] = px["ticker"].astype(str)
        px["date"] = pd.to_datetime(px["date"])

        fu = calcs_ds.to_table(filter=filt).to_pandas()
        if len(fu):
            fu = _prep_fundamentals(fu)
            # merge_asof needs the join keys globally sorted (pandas 2.1)
            panel = pd.merge_asof(px.sort_values("date"),
                                  fu.sort_values("available_date"),
                                  left_on="date", right_on="available_date",
                                  by="ticker", direction="backward")
        else:
            panel = _empty_fund_frame(px)

        panel["sector"] = panel["company_id"].map(sector_map).fillna("unknown")
        panel = _add_returns(panel)
        panel["has_suffix"] = panel["ticker"].str.contains(r"[.\-]", regex=True)
        panel = panel.rename(columns={**FACTOR_RENAME, **FUND_META})
        panel["year"] = panel["date"].dt.year

        for year, grp in panel.groupby("year"):
            ydir = out_dir / f"year={year}"
            ydir.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.Table.from_pandas(grp.drop(columns=["year"]),
                                                preserve_index=False),
                           ydir / f"batch-{b:03d}.parquet")
        report["batches"] += 1
        report["rows"] += len(panel)
        dmin, dmax = panel["date"].min(), panel["date"].max()
        if report["date_min"] is None or dmin < report["date_min"]:
            report["date_min"] = dmin
        if report["date_max"] is None or dmax > report["date_max"]:
            report["date_max"] = dmax
        print(f"  batch {b}: {len(batch)} tickers, {len(panel):,} rows",
              flush=True)

    report["date_min"] = str(report["date_min"])
    report["date_max"] = str(report["date_max"])
    return report
