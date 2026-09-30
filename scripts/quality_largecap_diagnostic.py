"""One-off diagnostic: which quality metrics fail on large caps, and is it
a coverage artifact? Compares per-factor rank ICs (broad vs large-cap
universe) and per-factor coverage for the 8 exact quality metrics.
"""
import gc

import pandas as pd
import pyarrow.dataset as ds

from borealis.backtest import panel_backtest as pb
from borealis.lab import preprocess, ic
from borealis.lab.run import load_lab_frame, MIN_VALID_PER_DATE

PANEL = "data/processed/intrinio/panel"
QUALITY_FACTORS = ["roe", "roa", "gross_margin", "profit_margin",
                   "fcf_margin", "debt_to_equity", "debt_ebitda",
                   "interest_coverage"]

all_dates = pb.panel_trading_dates(PANEL)
month_ends = pb.month_end_dates(all_dates)
lc = pb.large_cap_universe(PANEL, month_ends, top_n=1000)
lc["date"] = pd.to_datetime(lc["date"]).dt.normalize()

dataset = ds.dataset(PANEL, format="parquet", partitioning="hive")
avail = [f for f in QUALITY_FACTORS
         if f in preprocess.available_factors(dataset.schema.names)]
print("quality factors in panel:", avail, flush=True)

for f in avail:
    frame = load_lab_frame(PANEL, month_ends, [f], need_returns=True)
    frame = preprocess.add_lab_zscores(frame, [f])
    zc = "z_" + f
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame = frame.merge(lc[["date", "ticker"]].assign(is_lc=True),
                        on=["date", "ticker"], how="left")
    frame["is_lc"] = frame["is_lc"].fillna(False).astype(bool)
    for label, sub in [("broad", frame), ("largecap", frame[frame["is_lc"]])]:
        cov = sub[zc].notna().mean()
        outs = []
        for h, col in [(21, "ret_fwd_21d"), (63, "ret_fwd_63d")]:
            tmp = sub[["date", zc, col]].dropna().rename(
                columns={zc: "z", col: "f"})
            counts = tmp.groupby("date").size()
            ok = counts[counts >= MIN_VALID_PER_DATE].index
            if len(ok) < 10:
                outs.append(f"{h}d n/a")
                continue
            sm = ic.ic_summary(ic.ic_series(tmp[tmp["date"].isin(ok)], "z", "f"))
            outs.append(f"{h}d IC={sm['mean']:+.4f} t={sm['tstat']:+.2f}")
        print(f"{f:16s} {label:8s} cov={cov:.2f} " + " ".join(outs), flush=True)
    del frame
    gc.collect()
