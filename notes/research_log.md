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

## Quarterly review prompts

- Which drivers (value / momentum / lowvol) produced the most watch/deep-dive verdicts? Which produced passes?
- Did ★ new entries deserve their promotion?
- Any pattern in passes that suggests a sleeve blind spot? (Lab input.)
- Did any deep-dive name move materially? Direction and magnitude, no narrative.
