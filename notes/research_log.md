# Borealis research log

The log that closes the loop: lab → engine → workflow → back to the lab.
The ranking orders attention; this file records what the attention found.

## The monthly routine

1. **Rank** — `PYTHONPATH=src python scripts/rank.py --live --asof <date> --top 25 --out data/processed/scores_live_<date>.csv`
2. **Filter** — `PYTHONPATH=src python scripts/shortlist.py --top 15` → `data/processed/shortlist_<date>.md`
3. **Research** — pick names from the shortlist (top-down, or ★ new entries first). For each: one screen (30–60 min) or a deep dive; record below.
4. **Log** — one line per name: thesis, verdict, date. Revisit outcomes quarterly; patterns in the log are lab input.

## Verdicts

- **pass** — looked, not interested. One-line reason.
- **watch** — interesting but not now. Note the trigger that would change it.
- **deep-dive** — worth real hours. Thesis in one line.

## Log

| date | ticker | verdict | thesis / notes |
|------|--------|---------|----------------|
|      |        |         |                |

### October 2026 shortlist — DRAFT (2026-10-05, ranking asof 2026-09-30)

Same 15 names as September (no fresh ranking run; no ★ new entries). Every line below is a draft starting point — mark, edit, or replace as you research.

| ticker | draft verdict | draft thesis |
|--------|---------------|--------------|
| AES | deep-dive | Cheapest multiple on the board (P/E 5.6) in a defensive sector — find out what the market is pricing in. |
| GM | watch | Value flag on price action, not earnings (P/E 35.6, P/S 0.4) — check whether the P/E spike is one-off charges first. |
| FDX | watch | Classic cyclical value; the question is where we are in the freight cycle. |
| CNC | deep-dive | Rank rests on price-to-sales with no meaningful earnings multiple — Medicaid/regulatory exposure is the make-or-break question. |
| BG | watch | Agribusiness at P/S 0.2; commodity-cycle earnings — check grain/oilseed margin outlook. |
| CAH | watch | Thin-margin health-care distributor; the value case needs a margin or volume story. |
| PRU | watch | Insurer value at P/E 9.6 — check rate sensitivity and book-value trend. |
| EIX | watch | Momentum flag on a name 37% below its high — rebound or value trap; check the California wildfire/regulatory overhang. |
| F | watch | Deep value with no earnings multiple, 30% off highs — balance sheet and EV-transition capex are the questions. |
| TGT | watch | Momentum near 52-week highs — consumer health into the holiday quarter is the swing factor. |
| CTSH | deep-dive | Cheapest tech name, a third below highs (P/E 8.3) — AI-disruption fear vs. actual bookings is the question. |
| HPQ | watch | PC-cycle exposure at P/E 10.2 — check print vs. personal-systems mix. |
| SWK | watch | Highest multiple of the value cluster (P/E 23.0) — earnings have to justify the rank. |
| DAL | watch | Airline value is fuel-price and demand-cycle dependent — check unit-revenue trend. |
| PSX | watch | Refiner at P/E 9.6 — crack-spread cycle drives everything here. |

## Quarterly review prompts

- Which drivers (value / momentum / lowvol) produced the most watch/deep-dive verdicts? Which produced passes?
- Did ★ new entries deserve their promotion?
- Any pattern in passes that suggests a sleeve blind spot? (Lab input.)
- Did any deep-dive name move materially? Direction and magnitude, no narrative.
