"""One-off: individual-factor ICs for the lab comparisons (beta vs vol, pe vs earn_yield).

Lean version: loads only the columns needed for one factor at a time.
"""
import gc

import pandas as pd
import pyarrow.dataset as ds

from borealis.backtest import panel_backtest as pb
from borealis.lab import preprocess, price_proxies, ic
from borealis.lab.run import PROXY_FACTORS, load_lab_frame, MIN_VALID_PER_DATE

PANEL = "data/processed/intrinio/panel"
PRICES = "data/processed/intrinio/prices_clean.parquet"

all_dates = pb.panel_trading_dates(PANEL)
month_ends = pb.month_end_dates(all_dates)

for f in ["beta_252d", "vol_126d", "pe", "earn_yield", "ps", "pb", "ev_ebitda"]:
    if f in PROXY_FACTORS:
        frame = load_lab_frame(PANEL, month_ends, [], need_returns=True)
        prox = price_proxies.compute_price_proxies(PRICES, month_ends)
        frame = frame.merge(prox[["ticker", "date", f]], on=["ticker", "date"],
                            how="left")
        factors = [f]
    else:
        frame = load_lab_frame(PANEL, month_ends, [f], need_returns=True)
        factors = [f]
    frame = preprocess.add_lab_zscores(frame, factors)
    zc = "z_" + f
    for h, col in [(21, "ret_fwd_21d"), (63, "ret_fwd_63d")]:
        tmp = frame[["date", zc, col]].dropna().rename(columns={zc: "z", col: "f"})
        counts = tmp.groupby("date").size()
        ok = counts[counts >= MIN_VALID_PER_DATE].index
        s = ic.ic_series(tmp[tmp["date"].isin(ok)], "z", "f")
        sm = ic.ic_summary(s)
        print(f"{f:12s} {h:3d}d IC={sm['mean']:+.4f} t={sm['tstat']:+.2f} "
              f"hit={sm['hit_rate']:.2f} n={sm['n']}", flush=True)
    del frame
    gc.collect()
