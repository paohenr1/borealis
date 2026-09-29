"""Live universe builder: workbook-compatible frame from Intrinio bulk files.

Builds the same 19-column frame as ``loader.load_universe()`` plus the three
quality columns (``roe``, ``fcf_margin``, ``debt_to_equity``), for the ~520
index-constituent tickers in ``data/raw/universe_520.csv``, sourced from the
Intrinio bulk products (US Stock Prices 5yr, US Fundamentals 5yr, US Company
Metadata) under ``data/raw/intrinio/<date>/``.

SECTOR MAPPING (documented discovery + choice):
    Intrinio's company metadata does NOT carry GICS sectors. It carries SIC
    divisions (SECTOR_NAME, 17 coarse values like "Manufacturing" -- which
    lumps Apple, J&J, Tesla and Caterpillar together) and SIC industry groups
    (INDUSTRY_GROUP_NAME, ~hundreds of granular values like "Pharmaceutical
    Preparations"). The 17 divisions are too coarse to reproduce the
    workbook's 11 economic buckets faithfully, so this module maps the 152
    INDUSTRY_GROUP_NAME values observed for the live universe to the 11
    slugs. Every assignment is an explicit, auditable entry in SECTOR_MAP;
    anything unmapped raises ValueError (fail loud, never silently bucketed).
    Judgment calls, all documented here:
      - telecom/media groups ("Telephone Communications",
        "Radio & Tv Broadcasters", "Cable And Other Pay Tv Services",
        "Newspapers – Publishing-Printing", "Services – Advertising",
        "Services – Video Rental" (Netflix), "Services – Misc. Entertainment"
        (Disney)) -> "telecommunication", the workbook's legacy bucket and
        the closest slug to GICS Communication Services.
      - "Accident And Health Insurance" -> health_care: 5 of 7 names are
        managed-care (UNH, ELV, HUM, CI, CNC); AFL/PFG are the compromise.
      - "Services – Misc. Business Services" -> industrials (DoorDash/Akamai
        are the compromises); "Services – Computer Processing, Data
        Preparation And Processing" -> industrials (Workday/Reddit compromises).
      - "Misc. Measuring And Controlling Devices" -> industrials (Thermo
        Fisher/Trimble compromises); "Special Industry Machinery" ->
        technology (Pentair compromise); "Rolling, Drawing & Extruding Of
        Nonferrous Metals" -> industrials (Corning/Howmet compromises).
      - "Paper And Allied Products" -> materials (Kimberly-Clark compromise);
        "Soap & Other Detergents" -> consumer_staples (Ecolab compromise).
      - "Retail – Retail-Building Materials, Hardware, Garden Supply" ->
        consumer_discretionary (Fastenal/Sherwin-Williams compromises).
      - "Retail – Non-Store Retailers" -> consumer_discretionary (CDW
        compromise); "Apparel And Other Finished Products" ->
        consumer_discretionary (Cintas compromise).
      - "Wholesale – Groceries & Related Products" -> consumer_staples
        (Domino's compromise); "Services – Services To Dwellings & Other
        Buildings" -> consumer_discretionary (Rollins compromise).
      - "Services – Consumer Credit Reporting Agencies, Collection Services"
        -> industrials; "Misc. Publishing" (Thomson Reuters) -> industrials;
        "Household Appliances" (A.O. Smith) -> industrials, all per GICS.
      - "Services – Management, Public Relations, Consulting" (Gartner) ->
        technology per GICS.

TICKER NORMALIZATION (documented):
    The three bulk products use different ticker conventions. Prices use
    dots (BRK.B, BF.B); metadata/calculations/statements use hyphens
    (BRK-B). Universe tickers are normalized dot->hyphen when joining
    metadata/calculations/statements; prices join on the universe form.
    Five names need a same-issuer fallback because the vendor tracks only
    the other listing (documented, same company -- never a different one):
      BF.B -> BF-A (Brown-Forman; vendor tracks class A only),
      FOX -> FOXA, GOOG -> GOOGL, NWS -> NWSA (other share class),
      MAA -> MAAI (vendor ticker discrepancy; same REIT, CIK 912595).
    Output tickers always use the universe (Wikipedia) form.

METRIC SOURCES (verified against the 2026-09-29 bulk headers; missing -> NaN,
never invented or substituted):
    price            <- CLOSE (raw close) on the latest trading date per ticker
    high_52w/low_52w <- FIFTY_TWO_WEEK_HIGH / FIFTY_TWO_WEEK_LOW on that row
    market_cap       <- marketcap (TTM calculation, latest available vintage)
    pe_ratio         <- pricetoearnings
    ps_ratio         <- pricetorevenue
    peg_ratio        <- NO VENDOR TAG in the bulk -> NaN. The value factor's
                        existing missing-data path (sector-median imputation)
                        absorbs it; value degrades to P/E + P/S.
    sales_growth_q   <- YoY quarterly revenue growth, derived from quarterly
                        income-statement rows: totalrevenue(Q) /
                        totalrevenue(Q same quarter prior year) - 1. This is
                        the standard "trailing quarterly sales growth" the
                        growth factor expects. NaN if either quarter missing.
    trailing_beta    <- NO VENDOR TAG in the bulk -> 252-trading-day OLS
                        regression beta of daily log returns on split/
                        dividend-adjusted closes vs SPY, from the price bulk.
                        NaN if SPY/history insufficient.
    roe              <- roe (TTM calculation)
    fcf_margin       <- freecashflow (TTM, "Free Cash Flow to Firm") /
                        TTM revenue, where TTM revenue = sum of the latest 4
                        quarterly totalrevenue rows. NaN if either leg missing.
    debt_to_equity   <- debttoequity ("Debt to Equity", TTM calculation)
    last_qtr         <- "QX YYYY" of the latest quarterly income row
    currency         <- "USD" (US-comp bulk)
    company          <- NAME from company metadata
    sector_raw       <- INDUSTRY_GROUP_NAME as published by Intrinio

Snapshot semantics: the latest price date available in the bulk files is the
snapshot date (printed at build time); calculations use the latest TTM vintage
per ticker by (available_date, period rank), same discipline as the PIT panel.
Tickers in the universe file with no price row are excluded with a loud
warning and reported in the returned coverage dict -- never invented.
"""
from __future__ import annotations

import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# Calculation tags in the US_*_CALCULATIONS bulk files, verified 2026-09-29.
# Each entry lists candidate tags in preference order; the first tag actually
# present wins. An empty resolution means "no vendor tag" -> NaN or the
# documented derivation above.
DIRECT_TAGS: dict[str, list[str]] = {
    "market_cap": ["marketcap"],
    "pe_ratio": ["pricetoearnings"],
    "ps_ratio": ["pricetorevenue"],
    "peg_ratio": ["peg_ratio", "pegratio"],   # absent -> NaN (documented)
    "roe": ["roe"],
    "freecashflow": ["freecashflow"],
    "beta": ["beta"],                        # absent -> regression fallback
    "debt_to_equity": ["debttoequity"],
}

REVENUE_TAG = "totalrevenue"  # quarterly income statements, INDU + FIN
_QNUM = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

# Workbook column order, then the three quality columns.
WORKBOOK_COLS = [
    "n", "i", "company", "ticker", "currency", "last_qtr", "price",
    "market_cap", "high_52w", "low_52w", "pct_below_52w_high",
    "pct_above_52w_low", "ps_ratio", "pe_ratio", "sales_growth_q",
    "peg_ratio", "trailing_beta", "sector_raw", "sector",
]
QUALITY_COLS = ["roe", "fcf_margin", "debt_to_equity"]
LIVE_COLS = WORKBOOK_COLS + QUALITY_COLS

# Intrinio INDUSTRY_GROUP_NAME -> workbook sector slug (152 groups, verified
# against the 2026-09-29 bulk for the live universe; see module docstring).
# Generated by /tmp/gen_sector_map.py from verbatim bulk strings -- do not
# hand-edit; regenerate if the universe or bulk changes.
SECTOR_MAP = {
    # ---- technology (12) ----
    'Communication Equipment': 'technology',
    'Computer & Office Equipment': 'technology',
    'Computer Integrated Systems Design': 'technology',
    'Electronic Components & Accessories': 'technology',
    'Instruments For Measuring & Testing Of Electricity & Electrical Instruments': 'technology',
    'Optical Instruments And Lenses': 'technology',
    'Radio & Tv Broadcasting & Communications Equipment': 'technology',
    'Services – Computer Programming And Data Processing': 'technology',
    'Services – Management, Public Relations, Consulting': 'technology',
    'Special Industry Machinery': 'technology',
    'Telephone And Telegraph Apparatus': 'technology',
    'Wholesale – Electronic Parts & Equipment': 'technology',
    # ---- health_care (11) ----
    'Accident And Health Insurance': 'health_care',
    'Biological Products, Except Diagnostic Substances': 'health_care',
    'In Vitro, In Vivo Diagnostic Substances': 'health_care',
    'Lab Analytical Instruments': 'health_care',
    'Ophthalmic Goods': 'health_care',
    'Pharmaceutical Preparations': 'health_care',
    'Services – Research, Development, Testing Labs': 'health_care',
    'Services –\xa0Health': 'health_care',
    'Surgical, Medical, And Dental Instruments And Supplies': 'health_care',
    'Wholesale – Drugs & Drug Proprietaries': 'health_care',
    'Wholesale – Medical, Dental & Hospital Equipment': 'health_care',
    # ---- financials (8) ----
    'Financial Services': 'financials',
    'Fire, Marine & Casualty Insurance': 'financials',
    'Insurance Agents, Brokers & Service': 'financials',
    'Life Insurance': 'financials',
    'Misc. Insurance Carriers': 'financials',
    'National Commercial Banks': 'financials',
    'Security And Commodity Brokers, Dealers, Exchanges & Services': 'financials',
    'State Commercial Banks – Fed Reserve System': 'financials',
    # ---- energy (7) ----
    'Crude Petroleum & Natural Gas': 'energy',
    'Misc. Oil & Gas Field Services': 'energy',
    'Natural Gas Transmission': 'energy',
    'Natural Gas Transmission & Distribution': 'energy',
    'Oil & Gas Field Machinery & Equipment': 'energy',
    'Oil Royalty Traders': 'energy',
    'Petroleum Refining': 'energy',
    # ---- industrials (42) ----
    'Air Conditioning, Warm Air Heating And Refrigeration Equipment': 'industrials',
    'Air Transportation': 'industrials',
    'Aircraft': 'industrials',
    'Aircraft & Parts': 'industrials',
    'Aircraft Engines & Engine Parts': 'industrials',
    'Arrangement Of Transportation Of Freight And Cargo': 'industrials',
    'Automatic Controls For Regulating Residential & Commercial Environments & Appliances ': 'industrials',
    'Construction Machinery & Equipment': 'industrials',
    'Construction – Special Contractors': 'industrials',
    'Construction, Mining & Material Handling Machinery & Equipment': 'industrials',
    'Cutlery, Hand Tools And General Hardware': 'industrials',
    'Electrical Industrial Apparatus': 'industrials',
    'Electronic & Other Electrical Equipment': 'industrials',
    'Engines & Turbines': 'industrials',
    'Farm And Garden Machinery And Equipment': 'industrials',
    'General Industrial Machinery & Equipment': 'industrials',
    'Guided Missiles And Space Vehicles And Parts': 'industrials',
    'Heating Equipment & Plumbing Fixtures': 'industrials',
    'Heavy Construction – Not Building Contractors': 'industrials',
    'Household Appliances': 'industrials',
    'Industrial Measurement Instruments & Related Products': 'industrials',
    'Misc. Aircraft Parts & Auxiliary Equipment': 'industrials',
    'Misc. Fabricated Metal Products': 'industrials',
    'Misc. Industrial And Commercial Equipment And Machinery': 'industrials',
    'Misc. Measuring And Controlling Devices': 'industrials',
    'Misc. Publishing': 'industrials',
    'Ordnance & Accessories': 'industrials',
    'Railroad Equipment': 'industrials',
    'Railroads, Line-Haul Operating': 'industrials',
    'Rolling, Drawing & Extruding Of Nonferrous Metals': 'industrials',
    'Search, Detection, Navigation, Guidance': 'industrials',
    'Services – Computer Processing, Data Preparation And Processing': 'industrials',
    'Services – Consumer Credit Reporting Agencies, Collection Services': 'industrials',
    'Services – Engineering, Accounting, Research, Management': 'industrials',
    'Services – Equipment Rental And Leasing': 'industrials',
    'Services – Misc. Business Services': 'industrials',
    'Services – Sanitary Services': 'industrials',
    'Services – Security': 'industrials',
    'Ship Building And Repairing': 'industrials',
    'Trucking & Courier Services, Except Air': 'industrials',
    'Wholesale – Durable Goods': 'industrials',
    'Wholesale – Hardware, Plumbing & Heating Equipment': 'industrials',
    # ---- materials (15) ----
    'Agricultural Production – Crops': 'materials',
    'Agriculture Chemicals': 'materials',
    'Blast Furnaces & Steel Works': 'materials',
    'Cement, Hydraulic': 'materials',
    'Gold & Silver Ores': 'materials',
    'Industrial Inorganic Chemicals': 'materials',
    'Industrial Organic Chemicals': 'materials',
    'Metal Cans And Shipping Containers': 'materials',
    'Metal Mining': 'materials',
    'Mining And Quarrying Nonmetallic Minerals': 'materials',
    'Misc. Manufacturing Industries': 'materials',
    'Paints': 'materials',
    'Paper And Allied Products': 'materials',
    'Paperboard Containers, Boxes, Drums, Tubs': 'materials',
    'Plastic Material & Synthetic Resin/Rubber': 'materials',
    # ---- consumer_staples (16) ----
    'Beverages': 'consumer_staples',
    'Bottled-Canned Soft Drinks': 'consumer_staples',
    'Canned & Preserved Fruits & Vegetables': 'consumer_staples',
    'Fats And Oils': 'consumer_staples',
    'Flour And Other Grain Mill Products': 'consumer_staples',
    'Food And Kindred Products': 'consumer_staples',
    'Meat Products': 'consumer_staples',
    'Misc. Food Preparations And Kindred Products': 'consumer_staples',
    'Perfumes, Cosmetics And Other Toilet Preparations': 'consumer_staples',
    'Retail – Drug & Proprietary Stores': 'consumer_staples',
    'Retail – Grocery Stores': 'consumer_staples',
    'Retail – Variety Stores': 'consumer_staples',
    'Soap & Other Detergents': 'consumer_staples',
    'Sugar And Confectionery Products': 'consumer_staples',
    'Tobacco Products': 'consumer_staples',
    'Wholesale – Groceries & Related Products': 'consumer_staples',
    # ---- consumer_discretionary (24) ----
    'Apparel And Other Finished Products': 'consumer_discretionary',
    'General Building Contractors – Residential': 'consumer_discretionary',
    'Hotels & Motels': 'consumer_discretionary',
    'Leather Tanning And Finishing': 'consumer_discretionary',
    'Motor Vehicle Parts & Accessories': 'consumer_discretionary',
    'Motor Vehicles & Passenger Car Bodies': 'consumer_discretionary',
    'Operative Builders': 'consumer_discretionary',
    'Retail – Apparel & Accessory Stores': 'consumer_discretionary',
    'Retail – Automotive And Home Supply Stores': 'consumer_discretionary',
    'Retail – Automotive Dealers And Gas Stations': 'consumer_discretionary',
    'Retail – Eating Places': 'consumer_discretionary',
    'Retail – Home Furniture And Equipment Stores': 'consumer_discretionary',
    'Retail – Lumber & Other Building Materials': 'consumer_discretionary',
    'Retail – Misc. Retail Stores': 'consumer_discretionary',
    'Retail – Non-Store Retailers (Catalogs, Etc.)': 'consumer_discretionary',
    'Retail – Radio, Tv And Consumer Electronic Stores': 'consumer_discretionary',
    'Retail – Retail-Building Materials, Hardware, Garden Supply': 'consumer_discretionary',
    'Rubber And Plastics Footwear': 'consumer_discretionary',
    'Services – Services To Dwellings & Other Buildings': 'consumer_discretionary',
    'Services –\xa0Amusement And Recreation': 'consumer_discretionary',
    'Toys': 'consumer_discretionary',
    'Transportation Services': 'consumer_discretionary',
    'Water Transport': 'consumer_discretionary',
    'Wholesale – Automotive Vehicles & Automotive Parts & Supplies': 'consumer_discretionary',
    # ---- telecommunication (8) ----
    'Cable And Other Pay Tv Services': 'telecommunication',
    'Misc. Communication Services': 'telecommunication',
    'Newspapers –\xa0Publishing-Printing': 'telecommunication',
    'Radio & Tv Broadcasters': 'telecommunication',
    'Services – Advertising': 'telecommunication',
    'Services –\xa0Misc. Entertainment': 'telecommunication',
    'Services –\xa0Video Rental': 'telecommunication',
    'Telephone Communications': 'telecommunication',
    # ---- utilities (6) ----
    'Cogeneration – Sm Power Producer': 'utilities',
    'Electric And Other Services Combined': 'utilities',
    'Electric Services': 'utilities',
    'Gas And Other Services Combined': 'utilities',
    'Natural Gas Distribution': 'utilities',
    'Water Supply': 'utilities',
    # ---- real_estate (3) ----
    'REIT': 'real_estate',
    'Real Estate': 'real_estate',
    'Real Estate Operators And Lessors': 'real_estate',
}

# Universe ticker -> bulk ticker for metadata/calculations/statements.
# Prices join on the universe form (dots: BRK.B); everything else normalizes
# dot->hyphen, then applies the same-issuer fallback below (documented in the
# module docstring; output tickers always use the universe form).
TICKER_ALIASES = {
    "BF-B": "BF-A",   # Brown-Forman: vendor tracks class A only
    "FOX": "FOXA",    # same issuer, other share class
    "GOOG": "GOOGL",  # same issuer, other share class
    "NWS": "NWSA",    # same issuer, other share class
    "MAA": "MAAI",    # vendor ticker discrepancy; same REIT (CIK 912595)
}


def bulk_ticker(t: str) -> str:
    """Ticker form used by metadata/calculations/statements for universe ticker t."""
    t = t.replace(".", "-")
    return TICKER_ALIASES.get(t, t)


def _bulk_want(tickers: set[str]) -> tuple[set[str], dict[str, list[str]]]:
    """(bulk ticker filter set, bulk ticker -> universe tickers)."""
    rev: dict[str, list[str]] = {}
    for t in tickers:
        rev.setdefault(bulk_ticker(t), []).append(t)
    return set(rev), rev


def _explode_to_universe(df: pd.DataFrame, rev: dict[str, list[str]],
                         col: str = "ticker") -> pd.DataFrame:
    """Duplicate bulk rows so each universe ticker resolving to a bulk ticker
    gets its own row labeled with the universe ticker."""
    parts = []
    for b, uni_tickers in rev.items():
        sub = df[df[col] == b]
        if sub.empty:
            continue
        for u in uni_tickers:
            s = sub.copy()
            s[col] = u
            parts.append(s)
    if not parts:
        return df.iloc[0:0]
    return pd.concat(parts, ignore_index=True)


_BETA_WINDOW = 252  # trading days for the fallback beta regression


# ---------------------------------------------------------------------------
# Sector mapping
# ---------------------------------------------------------------------------

def map_sector(industry_group: str) -> str:
    """Map an Intrinio INDUSTRY_GROUP_NAME to a workbook sector slug.

    Raises ValueError for any name not in SECTOR_MAP -- unmapped groups are
    never silently bucketed or dropped.
    """
    try:
        return SECTOR_MAP[industry_group]
    except KeyError:
        raise ValueError(
            f"unmapped Intrinio industry group {industry_group!r}; "
            f"add an explicit mapping to SECTOR_MAP in universe_live.py"
        ) from None


# ---------------------------------------------------------------------------
# Bulk readers (chunked; only universe tickers are retained)
# ---------------------------------------------------------------------------

def _iter_zip_csvs(raw_dir: Path, prefix: str, name_contains: str = ""):
    for zp in sorted(raw_dir.glob(f"{prefix}*.zip")):
        if name_contains and name_contains not in zp.name.upper():
            continue
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                if name.lower().endswith(".csv") and "key" not in name.lower():
                    with z.open(name) as f:
                        yield pd.read_csv(f, low_memory=False)


def _resolve_tags(df: pd.DataFrame) -> dict[str, str | None]:
    """Map each metric to the first candidate tag present in df's columns."""
    cols = {c.lower(): c for c in df.columns}
    resolved: dict[str, str | None] = {}
    for metric, candidates in DIRECT_TAGS.items():
        resolved[metric] = next((cols[c] for c in candidates if c in cols), None)
    return resolved


def load_companies(raw_dir: Path, tickers: set[str]) -> pd.DataFrame:
    """Company metadata for universe tickers: ticker, company, sector_raw, sector."""
    want, rev = _bulk_want(tickers)
    frames = []
    for df in _iter_zip_csvs(raw_dir, "companies"):
        df.columns = [c.lower() for c in df.columns]
        keep = [c for c in ("ticker", "name", "industry_group_name")
                if c in df.columns]
        if "ticker" not in keep:
            continue
        sub = df.loc[df["ticker"].isin(want), keep]
        if not sub.empty:
            frames.append(sub)
    if not frames:
        raise ValueError(f"no company metadata rows for {len(tickers)} tickers in {raw_dir}")
    co = pd.concat(frames, ignore_index=True).drop_duplicates("ticker")
    co = _explode_to_universe(co, rev).drop_duplicates("ticker")
    missing = tickers - set(co["ticker"])
    if missing:
        warnings.warn(f"[universe_live] {len(missing)} tickers missing from company "
                      f"metadata, e.g. {sorted(missing)[:5]}")
    co["sector"] = co["industry_group_name"].map(map_sector)  # raises on unmapped
    return co.rename(columns={"name": "company",
                              "industry_group_name": "sector_raw"})[
        ["ticker", "company", "sector_raw", "sector"]]


def load_latest_prices(raw_dir: Path, tickers: set[str]) -> pd.DataFrame:
    """Latest price row per ticker: price, high_52w, low_52w, price_date."""
    best: dict[str, pd.Series] = {}
    for df in _iter_zip_csvs(raw_dir, "stock_prices"):
        df.columns = [c.upper() for c in df.columns]
        need = {"TICKER", "DATE", "CLOSE", "FIFTY_TWO_WEEK_HIGH", "FIFTY_TWO_WEEK_LOW"}
        if not need.issubset(df.columns):
            raise ValueError(f"price bulk missing columns: {need - set(df.columns)}")
        sub = df.loc[df["TICKER"].isin(tickers),
                     ["TICKER", "DATE", "CLOSE", "FIFTY_TWO_WEEK_HIGH",
                      "FIFTY_TWO_WEEK_LOW"]].copy()
        if sub.empty:
            continue
        sub["DATE"] = pd.to_datetime(sub["DATE"], errors="coerce")
        sub = sub.dropna(subset=["DATE"]).sort_values("DATE")
        for t, grp in sub.groupby("TICKER"):
            row = grp.iloc[-1]
            if t not in best or row["DATE"] > best[t]["DATE"]:
                best[t] = row
    if not best:
        raise ValueError(f"no price rows for {len(tickers)} tickers in {raw_dir}")
    px = pd.DataFrame(best).T.reset_index(drop=True)
    return px.rename(columns={
        "TICKER": "ticker", "DATE": "price_date", "CLOSE": "price",
        "FIFTY_TWO_WEEK_HIGH": "high_52w", "FIFTY_TWO_WEEK_LOW": "low_52w",
    })


def _pit_available_date(df: pd.DataFrame) -> pd.Series:
    """PIT availability key: latest of filing_date / first_calculable_at.

    Replicates ``intrinio_bulk._calc_available`` so the live path uses the
    same point-in-time rule as the canonical panel build.
    """
    fd = pd.to_datetime(df["filing_date"].astype(str).str[:10], errors="coerce")
    fc = pd.to_datetime(df["first_calculable_at"].astype(str).str[:10],
                        errors="coerce")
    avail = fd.fillna(fc)
    both = fd.notna() & fc.notna()
    avail.loc[both] = pd.concat([fd, fc], axis=1).max(axis=1)[both]
    return avail


def load_latest_calculations(raw_dir: Path, tickers: set[str]) -> tuple[pd.DataFrame, dict]:
    """Latest TTM calculation vintage per ticker (by available_date, then period rank)."""
    rank = {"FY": 3, "Q3TTM": 2, "Q2TTM": 1, "Q1TTM": 0}
    want, rev = _bulk_want(tickers)
    frames = []
    for df in _iter_zip_csvs(raw_dir, "US_", name_contains="CALCULATION"):
        df.columns = [c.lower() for c in df.columns]
        if "ticker" not in df.columns:
            continue
        sub = df.loc[df["ticker"].isin(want)].copy()
        if sub.empty:
            continue
        frames.append(sub)
    if not frames:
        raise ValueError(f"no calculation rows for {len(tickers)} tickers in {raw_dir}")
    calc = pd.concat(frames, ignore_index=True).copy()
    tags = _resolve_tags(calc)
    if not {"filing_date", "first_calculable_at"}.issubset(calc.columns):
        raise ValueError("calculation bulk missing filing_date/first_calculable_at")
    calc["available_date"] = _pit_available_date(calc)
    calc["period_rank"] = calc.get("fiscal_period", "").map(rank).fillna(-1)
    calc = calc.sort_values(["available_date", "period_rank"])
    latest = calc.groupby("ticker", as_index=False).tail(1)
    latest = _explode_to_universe(latest, rev)
    return latest, tags


def load_quarterly_revenue(raw_dir: Path, tickers: set[str],
                           snapshot_year: int) -> pd.DataFrame:
    """Per ticker: latest quarter (year/q), YoY quarterly revenue growth,
    and TTM revenue (sum of latest 4 quarterlies). NaN where not computable."""
    want, rev = _bulk_want(tickers)
    frames = []
    for df in _iter_zip_csvs(raw_dir, "US_", name_contains="INCOME_STATEMENT"):
        df.columns = [c.lower() for c in df.columns]
        need = {"ticker", "fiscal_year", "fiscal_period", REVENUE_TAG}
        if not need.issubset(df.columns):
            continue
        sub = df.loc[df["ticker"].isin(want), list(need)].copy()
        sub = sub[sub["fiscal_period"].isin(_QNUM)]
        if sub.empty:
            continue
        frames.append(sub)
    if not frames:
        raise ValueError(f"no quarterly income rows for {len(tickers)} tickers in {raw_dir}")
    inc = pd.concat(frames, ignore_index=True)
    inc["fiscal_year"] = pd.to_numeric(inc["fiscal_year"], errors="coerce")
    inc[REVENUE_TAG] = pd.to_numeric(inc[REVENUE_TAG], errors="coerce")
    inc = inc.dropna(subset=["fiscal_year", REVENUE_TAG])
    inc = inc[(inc["fiscal_year"] <= snapshot_year) & (inc[REVENUE_TAG] > 0)]
    inc["qnum"] = inc["fiscal_period"].map(_QNUM)
    inc = inc.sort_values(["fiscal_year", "qnum"]).drop_duplicates(
        ["ticker", "fiscal_year", "qnum"], keep="last")

    out = []
    for t, grp in inc.groupby("ticker"):
        grp = grp.sort_values(["fiscal_year", "qnum"]).reset_index(drop=True)
        last = grp.iloc[-1]
        ly, lq = int(last["fiscal_year"]), last["fiscal_period"]
        rev_val = float(last[REVENUE_TAG])
        py = grp[(grp["fiscal_year"] == ly - 1) & (grp["fiscal_period"] == lq)]
        growth = float(rev_val / float(py.iloc[0][REVENUE_TAG]) - 1) if not py.empty else np.nan
        ttm = grp.tail(4)
        ttm_rev = float(ttm[REVENUE_TAG].sum()) if len(ttm) == 4 else np.nan
        out.append({"ticker": t, "last_qtr": f"{lq} {ly}",
                    "sales_growth_q": growth, "ttm_revenue": ttm_rev})
    rev_df = pd.DataFrame(out)
    if rev_df.empty:
        return rev_df
    return _explode_to_universe(rev_df, rev)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def read_universe_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    if list(df.columns) != ["ticker", "index_membership"]:
        raise ValueError(f"unexpected universe columns: {list(df.columns)}")
    if not (515 <= len(df) <= 525):
        raise ValueError(f"universe has {len(df)} tickers, expected 515-525")
    ok = {"SP500", "NASDAQ100", "DOW"}
    bad = df[~df["index_membership"].str.split(r"\|").map(lambda p: set(p) <= ok and bool(p))]
    if not bad.empty:
        raise ValueError(f"bad index_membership values: {bad['index_membership'].unique()}")
    return df


def _fallback_beta(raw_dir: Path, tickers: set[str], price_date: pd.Timestamp) -> pd.Series:
    """252-day regression beta vs SPY from the price bulk. NaN where unavailable.

    Uses split/dividend-adjusted closes: raw closes embed split/dividend
    jumps that corrupt the regression (e.g. NVDA's 10:1 split in 2024).
    Data-quality quarantine: a series with a single-day |log return| > 1.0
    (ticker contamination or bad ticks in the bulk) gets NaN, not a garbage
    OLS estimate."""
    rets: dict[str, pd.Series] = {}
    start = price_date - pd.Timedelta(days=400)
    for df in _iter_zip_csvs(raw_dir, "stock_prices"):
        df.columns = [c.upper() for c in df.columns]
        if "ADJ_CLOSE" not in df.columns:
            raise ValueError("price bulk missing ADJ_CLOSE for beta fallback")
        want = tickers | {"SPY"}
        sub = df.loc[df["TICKER"].isin(want),
                     ["TICKER", "DATE", "ADJ_CLOSE"]].copy()
        if sub.empty:
            continue
        sub["DATE"] = pd.to_datetime(sub["DATE"], errors="coerce")
        sub = sub.dropna(subset=["DATE"])
        sub = sub[(sub["DATE"] >= start) & (sub["DATE"] <= price_date)]
        for t, grp in sub.groupby("TICKER"):
            s = grp.sort_values("DATE").drop_duplicates("DATE").set_index("DATE")["ADJ_CLOSE"]
            s = pd.to_numeric(s, errors="coerce").dropna()
            prev = rets.get(t)
            rets[t] = s if prev is None else pd.concat([prev, s]).sort_index().pipe(
                lambda x: x[~x.index.duplicated(keep="last")])
    if "SPY" not in rets:
        warnings.warn("[universe_live] SPY not in price bulk; trailing_beta -> NaN")
        return pd.Series(np.nan, index=list(tickers), name="trailing_beta")
    spy = np.log(rets["SPY"] / rets["SPY"].shift(1)).dropna().tail(_BETA_WINDOW)
    out = {}
    for t in tickers:
        if t not in rets:
            out[t] = np.nan
            continue
        r = np.log(rets[t] / rets[t].shift(1)).dropna().tail(_BETA_WINDOW)
        # Data-quality quarantine: a single-day |log return| > 1.0 (a 172%
        # move) cannot occur in a clean split-adjusted large-cap series --
        # the bulk has ticker contamination (e.g. BNY interleaves two
        # securities) and bad ticks (e.g. MRNA +177% for one day). OLS beta
        # is meaningless on such a series, so quarantine to NaN (the lowvol
        # factor imputes the sector median) rather than emit a garbage beta.
        if r.abs().max() > 1.0:
            warnings.warn(f"[universe_live] {t}: extreme daily move "
                          f"(|log ret|={r.abs().max():.2f}); beta -> NaN")
            out[t] = np.nan
            continue
        both = pd.concat([r, spy], axis=1, join="inner").dropna()
        if len(both) < 60 or both.iloc[:, 1].var() == 0:
            out[t] = np.nan
        else:
            out[t] = both.iloc[:, 0].cov(both.iloc[:, 1]) / both.iloc[:, 1].var()
    return pd.Series(out, name="trailing_beta")


def build_live_universe(universe_csv: str | Path,
                        raw_dir: str | Path) -> tuple[pd.DataFrame, dict]:
    """Build the workbook-compatible live frame.

    Returns (frame, coverage) where coverage reports the snapshot date, row
    count, tickers excluded for missing data, and per-metric NaN counts.
    """
    raw_dir = Path(raw_dir)
    uni = read_universe_csv(universe_csv)
    tickers = set(uni["ticker"])
    print(f"[universe_live] universe={len(tickers)} raw_dir={raw_dir}")

    co = load_companies(raw_dir, tickers)
    px = load_latest_prices(raw_dir, tickers)
    calc, tags = load_latest_calculations(raw_dir, tickers)

    missing_px = sorted(tickers - set(px["ticker"]))
    if missing_px:
        warnings.warn(f"[universe_live] excluding {len(missing_px)} tickers with no "
                      f"price data: {missing_px[:10]}")
    keep = sorted(tickers - set(missing_px))

    snap_date = px["price_date"].max()
    print(f"[universe_live] snapshot price_date={snap_date.date()} "
          f"tickers_with_prices={len(keep)}")

    rev = load_quarterly_revenue(raw_dir, set(keep), snap_date.year)

    frame = pd.DataFrame({"ticker": keep})
    frame = frame.merge(co, on="ticker", how="left")
    frame = frame.merge(px[["ticker", "price", "high_52w", "low_52w"]],
                        on="ticker", how="left")
    frame = frame.merge(rev, on="ticker", how="left")
    calc = calc.set_index("ticker")

    def tag(metric: str) -> pd.Series:
        col = tags.get(metric)
        if col is None:
            return pd.Series(np.nan, index=frame["ticker"])
        return frame["ticker"].map(calc[col])

    frame["market_cap"] = tag("market_cap")
    frame["pe_ratio"] = tag("pe_ratio")
    frame["ps_ratio"] = tag("ps_ratio")
    frame["peg_ratio"] = tag("peg_ratio")  # NaN: no vendor tag (documented)
    frame["roe"] = tag("roe")

    fcf = pd.to_numeric(tag("freecashflow"), errors="coerce")
    trev = pd.to_numeric(frame["ttm_revenue"], errors="coerce")
    frame["fcf_margin"] = (fcf / trev).where(fcf.notna() & trev.notna() & (trev != 0))
    frame["debt_to_equity"] = tag("debt_to_equity")

    if tags.get("beta") is not None:
        frame["trailing_beta"] = tag("beta")
    else:
        warnings.warn("[universe_live] no beta tag in bulk; using 252d regression beta vs SPY")
        frame["trailing_beta"] = frame["ticker"].map(
            _fallback_beta(raw_dir, set(keep), snap_date))

    frame["last_qtr"] = frame["last_qtr"].where(frame["last_qtr"].notna(), np.nan)
    frame["currency"] = "USD"
    frame["pct_below_52w_high"] = frame["price"] / frame["high_52w"] - 1
    frame["pct_above_52w_low"] = frame["price"] / frame["low_52w"] - 1
    frame = frame.sort_values(["sector", "ticker"]).reset_index(drop=True)
    frame["n"] = frame.groupby("sector").cumcount() + 1
    frame["i"] = ""

    missing_cols = [c for c in LIVE_COLS if c not in frame.columns]
    if missing_cols:
        raise ValueError(f"live frame missing columns: {missing_cols}")
    frame = frame[LIVE_COLS]

    coverage = {
        "snapshot_price_date": str(snap_date.date()),
        "universe_tickers": len(tickers),
        "rows": len(frame),
        "excluded_no_price": missing_px,
        "nan_counts": {c: int(frame[c].isna().sum()) for c in LIVE_COLS
                       if frame[c].isna().any()},
        "resolved_tags": {k: v for k, v in tags.items()},
    }
    print(f"[universe_live] rows={len(frame)} sectors={frame['sector'].nunique()} "
          f"excluded={len(missing_px)}")
    return frame, coverage


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe-csv", default="data/raw/universe_520.csv")
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    frame, coverage = build_live_universe(args.universe_csv, args.raw_dir)
    print("coverage:", coverage["nan_counts"])
    if args.out:
        frame.to_csv(args.out, index=False)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
