"""Chunked loader for Intrinio bulk downloads (prices, fundamentals, companies).

Reads the immutable zips under ``data/raw/intrinio/<date>/`` in streaming
chunks, validates schemas/dates/types, quarantines bad rows (never silently
drops), de-duplicates, and writes clean typed Parquet tables.

Key data facts established by inspection (2026-09-28, recorded here so the
pipeline's assumptions are explicit):

* Prices: ``CLOSE`` is the raw unadjusted close; ``ADJ_CLOSE`` is adjusted for
  splits AND dividends (total-return basis; verified on NVDA's 2024-06-10 10:1
  split and Agilent dividend ex-dates where ``ADJ_FACTOR == 1 - div/close``).
  Returns computed on ``ADJ_CLOSE`` are total returns with dividends embedded.
* ~0.26% of (ticker, date) rows are duplicated across two SECURITY_IDs with
  identical CLOSE/VOLUME but different ADJ_CLOSE vintages. De-dup keeps the
  row from the longest-lived security (deterministic tie-break).
* Fundamentals carry three vintages: ``reported`` (as originally filed),
  ``restated`` (older periods, values as republished in later filings), and
  ``calculated`` (Intrinio TTM/YTD derivations). reported/restated keys are
  disjoint -- older periods exist ONLY as restated. Restated rows carry the
  *republication* filing date, so ``filing_date`` is a valid point-in-time
  availability key, but values embed future revisions (documented caveat).
* Delisted securities ARE present (1,455 inactive company_ids have price
  rows); price histories terminate at delisting. Metadata delisting dates
  are noisy -- do not rely on them.
"""
from __future__ import annotations

import json
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------- schemas

PRICE_USECOLS = [
    "SECURITY_ID", "COMPANY_ID", "TICKER", "COMP_TICKER", "EXCH_TICKER",
    "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME",
    "ADJ_OPEN", "ADJ_HIGH", "ADJ_LOW", "ADJ_CLOSE", "ADJ_VOLUME",
    "ADJ_FACTOR", "EX_DIVIDEND", "SPLIT_RATIO",
    "FIFTY_TWO_WEEK_HIGH", "FIFTY_TWO_WEEK_LOW",
]

PRICE_NUMERIC = [
    "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME",
    "ADJ_OPEN", "ADJ_HIGH", "ADJ_LOW", "ADJ_CLOSE", "ADJ_VOLUME",
    "ADJ_FACTOR", "EX_DIVIDEND", "SPLIT_RATIO",
    "FIFTY_TWO_WEEK_HIGH", "FIFTY_TWO_WEEK_LOW",
]

COMPANY_USECOLS = [
    "ID", "TICKER", "NAME", "STOCK_EXCHANGE", "STATEMENT_TEMPLATE",
    "SECTOR_NAME", "INDUSTRY_GROUP_NAME", "STANDARDIZED_ACTIVE",
    "FIRST_STOCK_PRICE_DATE", "LAST_STOCK_PRICE_DATE",
]

# Factor inputs taken from the CALCULATIONS bulk files. Only columns present
# in BOTH the FIN and INDU templates are used (intersection enforced at load).
CALC_WANT = [
    "fundamental_id", "company_id", "ticker", "end_date", "fiscal_year",
    "fiscal_period", "filing_date", "first_calculable_at", "months",
    "pricetoearnings", "pricetobook", "pricetorevenue",
    "evtoebitda", "evtoebit", "evtofcff", "evtosales",
    "marketcap", "enterprisevalue", "freecashflow",
    "dividendyield", "earningsyield",
    "revenuegrowth", "ebitdagrowth", "ebitgrowth",
    "bookvaluepershare", "debttoebitda",
    "roe", "roa", "grossmargin", "operatingmargin", "ebitdamargin",
    "profitmargin", "currentratio", "assetturnover", "leverageratio",
    "ebittointerestex",  # interest coverage (financial health), added 2026-09-30
]

# TTM/FY rows give one trailing-twelve-months vintage per filing.
TTM_PERIODS = {"Q1TTM", "Q2TTM", "Q3TTM", "FY"}

CHUNK_ROWS = 400_000


def raw_dir_default() -> Path:
    return (Path(__file__).resolve().parents[4] / "data" / "raw"
            / "intrinio" / "2026-09-28")


def price_files(raw_dir: Path | str) -> list[Path]:
    files = sorted(Path(raw_dir).glob("stock_prices_uscomp_since_2020-01-24_file-*.zip"),
                   key=lambda p: int(p.stem.split("file-")[1]))
    if not files:
        raise FileNotFoundError(f"no price zips in {raw_dir}")
    return files


# ---------------------------------------------------------------- prices

def _pass1_security_stats(files: list[Path]) -> tuple[Counter, set[str]]:
    """Count rows per SECURITY_ID; find tickers spanning multiple files."""
    sec_counts: Counter = Counter()
    ticker_files: dict[str, set[int]] = {}
    for i, zpath in enumerate(files):
        with zipfile.ZipFile(zpath) as z, z.open(z.namelist()[0]) as f:
            for chunk in pd.read_csv(f, chunksize=CHUNK_ROWS, dtype=str,
                                     usecols=["TICKER", "SECURITY_ID"]):
                sec_counts.update(chunk["SECURITY_ID"])
                for t in chunk["TICKER"].unique():
                    ticker_files.setdefault(t, set()).add(i)
    cross = {t for t, fs in ticker_files.items() if len(fs) > 1}
    return sec_counts, cross


def _clean_price_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate + type a raw price chunk. Returns (clean, quarantined)."""
    missing = [c for c in PRICE_USECOLS if c not in df.columns]
    if missing:
        raise ValueError(f"price chunk missing columns: {missing}")
    df = df[PRICE_USECOLS].copy()

    df["date"] = pd.to_datetime(df["DATE"], format="%Y-%m-%d", errors="coerce")
    bad_date = df["date"].isna()
    for c in PRICE_NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # NaN / non-positive adj_close cannot produce returns -> quarantine
    bad_px = df["ADJ_CLOSE"].isna() | (df["ADJ_CLOSE"] <= 0)

    df["quarantine_reason"] = ""
    df.loc[bad_date, "quarantine_reason"] = "bad_date"
    bad_ticker = df["TICKER"].isna() | (df["TICKER"].astype(str).str.strip() == "")
    df.loc[~bad_date & bad_ticker, "quarantine_reason"] = "missing_ticker"
    df.loc[~bad_date & ~bad_ticker & bad_px, "quarantine_reason"] = "bad_adj_close"

    q = df.loc[df["quarantine_reason"] != ""].copy()
    df = df.loc[df["quarantine_reason"] == ""].copy()
    df = df.rename(columns={
        "TICKER": "ticker", "COMPANY_ID": "company_id",
        "SECURITY_ID": "security_id", "OPEN": "open", "HIGH": "high",
        "LOW": "low", "CLOSE": "close", "VOLUME": "volume",
        "ADJ_CLOSE": "adj_close", "ADJ_VOLUME": "adj_volume",
        "ADJ_FACTOR": "adj_factor", "EX_DIVIDEND": "ex_dividend",
        "SPLIT_RATIO": "split_ratio",
        "FIFTY_TWO_WEEK_HIGH": "high_52w", "FIFTY_TWO_WEEK_LOW": "low_52w",
    })
    keep = ["ticker", "company_id", "security_id", "date", "open", "high",
            "low", "close", "volume", "adj_close", "adj_volume",
            "adj_factor", "ex_dividend", "split_ratio", "high_52w", "low_52w"]
    return df[keep], q


def load_prices(raw_dir: Path | str, out_path: Path | str,
                quarantine_dir: Path | str | None = None) -> dict:
    """Stream all price zips -> clean Parquet. Returns a JSON-able report."""
    raw_dir, out_path = Path(raw_dir), Path(out_path)
    files = price_files(raw_dir)
    report: dict = {"files": len(files), "rows_in": 0, "rows_out": 0,
                    "dupes_dropped": 0, "quarantined": Counter()}

    print("[load_prices] pass 1: security stats ...", flush=True)
    sec_counts, cross_tickers = _pass1_security_stats(files)
    report["securities"] = len(sec_counts)
    report["cross_file_tickers"] = len(cross_tickers)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    spill: list[pd.DataFrame] = []   # rows for cross-file tickers, deduped at end
    quarantine_frames: list[pd.DataFrame] = []

    def _rank_key(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["_sec_n"] = df["security_id"].map(sec_counts).fillna(0).astype(int)
        return df.sort_values(["ticker", "date", "_sec_n", "security_id"],
                              ascending=[True, True, False, True])

    print("[load_prices] pass 2: clean + write ...", flush=True)
    for zpath in files:
        with zipfile.ZipFile(zpath) as z, z.open(z.namelist()[0]) as f:
            for chunk in pd.read_csv(f, chunksize=CHUNK_ROWS, dtype=str,
                                     usecols=lambda c: c in PRICE_USECOLS):
                report["rows_in"] += len(chunk)
                clean, q = _clean_price_frame(chunk)
                if len(q):
                    report["quarantined"].update(q["quarantine_reason"])
                    quarantine_frames.append(q)
                if not len(clean):
                    continue
                clean = _rank_key(clean)
                before = len(clean)
                clean = clean.drop_duplicates(["ticker", "date"], keep="first")
                report["dupes_dropped"] += before - len(clean)
                is_cross = clean["ticker"].isin(cross_tickers)
                if is_cross.any():
                    spill.append(clean[is_cross].drop(columns=["_sec_n"]))
                rest = clean[~is_cross].drop(columns=["_sec_n"])
                if len(rest):
                    table = pa.Table.from_pandas(rest, preserve_index=False)
                    if writer is None:
                        writer = pq.ParquetWriter(out_path, table.schema)
                    writer.write_table(table)
                    report["rows_out"] += len(rest)
        print(f"  {zpath.name} done", flush=True)

    if spill:
        sp = pd.concat(spill, ignore_index=True)
        sp = _rank_key(sp)
        before = len(sp)
        sp = sp.drop_duplicates(["ticker", "date"], keep="first").drop(columns=["_sec_n"])
        report["dupes_dropped"] += before - len(sp)
        table = pa.Table.from_pandas(sp, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_path, table.schema)
        writer.write_table(table)
        report["rows_out"] += len(sp)
    if writer is not None:
        writer.close()

    if quarantine_dir is not None and quarantine_frames:
        qdir = Path(quarantine_dir)
        qdir.mkdir(parents=True, exist_ok=True)
        qq = pd.concat(quarantine_frames, ignore_index=True)
        qq.to_parquet(qdir / "prices_quarantined.parquet", index=False)
    report["quarantined"] = dict(report["quarantined"])
    return report


# ---------------------------------------------------------------- companies

def load_companies(raw_dir: Path | str) -> pd.DataFrame:
    """Company metadata -> tidy frame (small enough to hold in memory)."""
    zpath = Path(raw_dir) / "companies.zip"
    with zipfile.ZipFile(zpath) as z, z.open("companies.csv") as f:
        df = pd.read_csv(f, dtype=str, keep_default_na=False,
                         usecols=lambda c: c in COMPANY_USECOLS)
    df = df.rename(columns={
        "ID": "company_id", "TICKER": "ticker", "NAME": "name",
        "STOCK_EXCHANGE": "exchange", "STATEMENT_TEMPLATE": "template",
        "SECTOR_NAME": "sector_name", "INDUSTRY_GROUP_NAME": "industry_group",
        "STANDARDIZED_ACTIVE": "is_active",
        "FIRST_STOCK_PRICE_DATE": "first_price_date",
        "LAST_STOCK_PRICE_DATE": "last_price_date",
    })
    df["is_active"] = df["is_active"] == "true"
    df["sector"] = df["sector_name"].str.strip().str.lower().str.replace(
        r"[^a-z0-9]+", "_", regex=True).str.strip("_")
    df.loc[df["sector"] == "", "sector"] = "unknown"
    df = df[df["company_id"].astype(str).str.strip() != ""]
    df = df.drop_duplicates(subset=["company_id"], keep="first")
    return df


# ---------------------------------------------------------------- fundamentals (calculations)

def calc_files(raw_dir: Path | str) -> list[Path]:
    files = sorted(Path(raw_dir).glob("*_CALCULATIONS.zip"))
    if not files:
        raise FileNotFoundError(f"no CALCULATIONS zips in {raw_dir}")
    return files


def _calc_available(df: pd.DataFrame) -> pd.DataFrame:
    """PIT availability key: latest of filing_date / first_calculable_at."""
    fd = pd.to_datetime(df["filing_date"].str[:10], errors="coerce")
    fc = pd.to_datetime(df["first_calculable_at"].str[:10], errors="coerce")
    df["available_date"] = fd.fillna(fc)
    both = fd.notna() & fc.notna()
    df.loc[both, "available_date"] = pd.concat([fd, fc], axis=1).max(axis=1)[both]
    return df


def load_calculations(raw_dir: Path | str, out_path: Path | str,
                      quarantine_dir: Path | str | None = None) -> dict:
    """Stream CALCULATIONS zips -> slim TTM/FY Parquet with PIT dates."""
    raw_dir = Path(raw_dir)
    files = calc_files(raw_dir)
    report: dict = {"files": [p.name for p in files], "rows_in": 0,
                    "rows_out": 0, "quarantined": Counter(),
                    "skipped_period": Counter(), "columns": []}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    qframes: list[pd.DataFrame] = []
    use_cols: list[str] | None = None

    for zpath in files:
        with zipfile.ZipFile(zpath) as z:
            csv_name = [n for n in z.namelist() if n.endswith(".csv")
                        and "KEY" not in n][0]
            with z.open(csv_name) as f:
                for chunk in pd.read_csv(f, chunksize=200_000, dtype=str,
                                         keep_default_na=False):
                    report["rows_in"] += len(chunk)
                    if use_cols is None:
                        use_cols = [c for c in CALC_WANT if c in chunk.columns]
                        report["columns"] = use_cols
                    chunk = chunk[[c for c in use_cols if c in chunk.columns]].copy()
                    n_period_all = chunk["fiscal_period"].value_counts()
                    chunk = chunk[chunk["fiscal_period"].isin(TTM_PERIODS)]
                    for p, n in n_period_all.items():
                        if p not in TTM_PERIODS:
                            report["skipped_period"][p] = \
                                report["skipped_period"].get(p, 0) + int(n)
                    if not len(chunk):
                        continue
                    chunk = _calc_available(chunk)
                    bad = chunk["available_date"].isna()
                    if bad.any():
                        qb = chunk[bad].copy()
                        qb["quarantine_reason"] = "no_availability_date"
                        report["quarantined"].update(qb["quarantine_reason"])
                        qframes.append(qb)
                        chunk = chunk[~bad]
                    if not len(chunk):
                        continue
                    id_cols = {"ticker", "company_id", "fundamental_id",
                               "fiscal_year", "fiscal_period"}
                    for c in use_cols:
                        if c in chunk.columns and c not in id_cols \
                                and c not in ("end_date", "filing_date",
                                              "first_calculable_at"):
                            chunk[c] = pd.to_numeric(chunk[c], errors="coerce")
                    chunk["end_date"] = pd.to_datetime(chunk["end_date"],
                                                       errors="coerce")
                    table = pa.Table.from_pandas(chunk, preserve_index=False)
                    if writer is None:
                        writer = pq.ParquetWriter(out_path, table.schema)
                    writer.write_table(table)
                    report["rows_out"] += len(chunk)
        print(f"  {zpath.name} done", flush=True)
    if writer is not None:
        writer.close()
    if quarantine_dir is not None and qframes:
        qdir = Path(quarantine_dir)
        qdir.mkdir(parents=True, exist_ok=True)
        pd.concat(qframes, ignore_index=True).to_parquet(
            qdir / "calculations_quarantined.parquet", index=False)
    report["quarantined"] = dict(report["quarantined"])
    report["skipped_period"] = dict(report["skipped_period"])
    return report
