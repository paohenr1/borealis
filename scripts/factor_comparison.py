"""Factor-level comparison: every scored variable's IC (21d/63d) and coverage
on the broad panel vs the large-cap universe, grouped by sleeve.
Writes data/processed/factor_comparison_2026-09-30.{csv,json}.
"""
import gc
import json

import pandas as pd
import pyarrow.dataset as ds

from borealis.backtest import panel_backtest as pb
from borealis.lab import preprocess, ic
from borealis.lab.run import load_lab_frame, MIN_VALID_PER_DATE

PANEL = "data/processed/intrinio/panel"
OUT = "data/processed/factor_comparison_2026-09-30"

SLEEVE_OF = {}
for sleeve, members in preprocess.SLEEVES.items():
    for m in members:
        SLEEVE_OF[m] = sleeve
DIAGNOSTICS = {"earn_yield": "value (diagnostic)",
               "vol_126d": "lowvol (diagnostic)",
               "fcf": "quality (diagnostic)",
               "leverage": "quality (diagnostic)",
               "bvps": "quality (diagnostic)",
               "asset_turnover": "quality (diagnostic)"}

all_dates = pb.panel_trading_dates(PANEL)
month_ends = pb.month_end_dates(all_dates)
lc = pb.large_cap_universe(PANEL, month_ends, top_n=1000)
lc["date"] = pd.to_datetime(lc["date"]).dt.normalize()
lc_pairs = lc[["date", "ticker"]].assign(is_lc=True)

factors = [f for f in preprocess.FACTOR_DIRECTION if f not in
           preprocess.DROPPED_FACTORS]
dataset = ds.dataset(PANEL, format="parquet", partitioning="hive")
factors = [f for f in factors if f in dataset.schema.names]
print(f"{len(factors)} factors", flush=True)

rows = []
for f in factors:
    frame = load_lab_frame(PANEL, month_ends, [f], need_returns=True)
    frame = preprocess.add_lab_zscores(frame, [f])
    zc = "z_" + f
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame = frame.merge(lc_pairs, on=["date", "ticker"], how="left")
    frame["is_lc"] = frame["is_lc"].fillna(False).astype(bool)
    row = {"factor": f,
           "sleeve": SLEEVE_OF.get(f, DIAGNOSTICS.get(f, "other"))}
    for label, sub in [("broad", frame), ("lc", frame[frame["is_lc"]])]:
        row[f"cov_{label}"] = round(float(sub[zc].notna().mean()), 4)
        for h, col in [(21, "ret_fwd_21d"), (63, "ret_fwd_63d")]:
            tmp = sub[["date", zc, col]].dropna().rename(
                columns={zc: "z", col: "f"})
            counts = tmp.groupby("date").size()
            ok = counts[counts >= MIN_VALID_PER_DATE].index
            if len(ok) < 10:
                row[f"ic{ h}_{label}"] = None
                row[f"t{h}_{label}"] = None
                continue
            sm = ic.ic_summary(ic.ic_series(tmp[tmp["date"].isin(ok)], "z", "f"))
            row[f"ic{h}_{label}"] = round(sm["mean"], 4)
            row[f"t{h}_{label}"] = round(sm["tstat"], 2)
    rows.append(row)
    print(f"done {f}", flush=True)
    del frame
    gc.collect()

df = pd.DataFrame(rows)
df.to_csv(OUT + ".csv", index=False)
df.to_json(OUT + ".json", orient="records", indent=1)
print(df[["factor", "sleeve", "ic21_broad", "t21_broad",
          "ic21_lc", "t21_lc"]].to_string(index=False))
