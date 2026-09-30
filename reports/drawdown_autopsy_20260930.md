# Borealis drawdown autopsy — 2026-09-30

Autopsy of the −36.6% max drawdown in the canonical 2026-09-28 backtest
(L/S Q5−Q1, 10 bps one-way, 80 monthly periods 2020-02 → 2026-09).
All figures recomputed from stored outputs in
`data/processed/backtest_first_2026-09-28/`; nothing hand-waved.
Quintile-membership characterization (Section 5) uses current
post-2026-09-29 signal definitions as an approximation — flagged where used.

## 1. Drawdown anatomy

| Item | Value |
|---|---|
| Peak | **2020-02-03** (equity 0.979) |
| Trough | **2021-02-01** (equity 0.621) |
| Depth | **−36.58%** |
| Recovery | **2022-09-01** (19 months trough→recovery) |
| Total underwater | **32 months** (12 down, 20 back up) |
| Window P&L, net | −37.9% over 13 monthly periods |
| Window cost drag | −0.4% (turnover 0.47/mo in-window vs 0.32 avg — elevated, but costs are **not** the story) |

Monthly spread returns inside the window:

| Trade date | Spread | Market backdrop |
|---|---|---|
| 2020-02-03 | −2.1% | pre-crash drift |
| 2020-03-02 | −0.1% | **COVID crash month — strategy essentially flat** |
| 2020-04-01 | −5.2% | rebound begins |
| 2020-05-01 | −6.6% | speculative rebound |
| 2020-06-01 | −5.9% | |
| 2020-07-01 | −4.2% | |
| 2020-08-03 | −0.5% | |
| 2020-09-01 | +1.8% | |
| 2020-10-01 | −0.0% | |
| 2020-11-02 | **−14.9%** | **Pfizer vaccine news (Nov 9) → violent junk/value rotation** |
| 2020-12-01 | −0.0% | |
| 2021-01-01 | −0.2% | |
| 2021-02-01 | **−7.7%** | **GME/meme mania peak (late Jan 2021)** |

The strategy survived the actual crash and bled out in the recovery.
Annual spread: 2020 −32.7% / 2021 +13.4% / 2022 +48.0% / 2023 −2.5% /
2024 +5.5% / 2025 +8.6% / 2026 +21.2% (partial). Trough→Sep 2026: **+146%**.

## 2. Leg decomposition — it was 100% the short book

| Leg | Window cumulative | Full-sample ann. | Own max DD |
|---|---|---|---|
| Q1 (short) | **+50.0%** → short side lost ~50% | −8.2%/yr | −62.3% |
| Q5 (long) | +0.2% (flat) | +0.6%/yr | −29.2% |
| Q2 / Q3 / Q4 | +31.3% / +18.5% / +11.1% | — | — |

- Q1–Q5 monthly correlation in-window: **+0.96** (full sample +0.86).
  The legs moved together; the spread collapsed because the junk quintile
  rallied ~50% while the quality quintile stood still.
- The return pattern across quintiles in-window is monotonically *inverted*
  (Q1 best, Q5 worst) — the model's ranking ran backwards for 12 months.
- The same signature recurs once more in-sample: **Jan 2023, −14.0%**,
  the second-worst month, with Q1 +16.8% vs Q5 +2.9% (the Jan-2023
  "everything rally" / short squeeze).

## 3. Sleeve attribution (window: Feb 2020 → Feb 2021)

| Sleeve | Weight | Window spread | Contrib (pts) | Sleeve own DD | Own DD trough |
|---|---|---|---|---|---|
| Yield | 0.15 | −21.0% | −3.15 | −43.0% | 2020-09 |
| LowVol | 0.10 | −25.4% | −2.54 | −26.1% | 2021-02 |
| Quality | 0.40 | −5.5% | −2.19 | −11.2% | 2025-09 |
| Value | 0.15 | −10.2% | −1.53 | −11.7% | 2025-10 |
| Momentum | 0.15 | −7.4% | −1.11 | −15.0% | 2023-01 |
| Size | 0.05 | −20.0% | −1.00 | −25.7% | 2021-02 |
| Growth | 0.00 | −8.5% | 0.00 | −27.9% | 2022-08 |

- **Every sleeve bled simultaneously** — a common-factor event, not an
  idiosyncratic sleeve failure. (Sleeve spreads are standalone Q5−Q1 per
  sleeve, so contributions are directional, not exact.)
- Worst in percentage terms: low-vol and yield — the two most
  "anti-speculation" sleeves, exactly what you'd expect to fail in a
  junk melt-up. Momentum's −7.4% is the classic post-crash momentum
  reversal (Mar-2020 winners/losers flipped).
- Sleeve DDs trough at *different* dates outside the window
  (quality 2025, momentum 2023) — sleeves fail independently in normal
  times; they failed *together* only in this window.

## 4. Market context

- **Mar 2020:** the COVID crash. Spread −0.1% — the factor book was
  roughly market-neutral through the crash itself.
- **Apr–Jul 2020:** unprecedented fiscal/monetary-fueled rebound led by
  the most speculative names. Steady −4 to −7%/mo bleed.
- **Nov 2020:** Pfizer vaccine announcement (Nov 9) triggered a violent
  rotation into beaten-down cyclicals and distressed names: −14.9%, the
  worst month in the sample.
- **Jan–Feb 2021:** meme-stock mania (GME peak late Jan). −7.7%.
- **Jan 2023 (echo):** post-2022-bear short squeeze / "everything rally":
  −14.0% on the same Q1-rips/Q5-flat signature.

## 5. What the short book actually was (approximation)

Recomputed quintile membership on the 13 window signal dates with current
signal definitions (sector-neutral z, qcut — same construction as the
backtest engine; metric sets revised since, so treat as directional):

| | Q1 (short) | Q5 (long) | Universe |
|---|---|---|---|
| Median market cap | **$602M** | $1,218M | $1,016M |
| Median price | **$12.34** | $24.74 | $22.79 |
| % sub-$5 | **29.8%** | 16.2% | 15.8% |

- Sector weights: no extreme concentration — Q1 mildly overweight
  services/manufacturing/mining vs universe (largest OW +7.9pp). The
  sector-neutral z-scoring did its job; this was a **within-sector**
  junk squeeze, not a sector bet gone wrong.
- Translation: the short book was smaller-cap, lower-priced, lower-quality
  names — precisely the cohort that rips hardest in speculative melt-ups.

## 6. Verdict: regime concentration — blunt version

**This is a regime-concentration problem, not scattered signal weakness.**

1. One continuous 12-month event (Feb 2020 → Feb 2021), single trough,
   full recovery by Sep 2022 — not multiple scattered episodes.
2. 100% short-leg driven: Q1 +50%, Q5 flat. The long book didn't fail;
   the ranking inverted because junk squeezed.
3. Timing maps exactly onto identifiable speculative melt-ups
   (rebound → vaccine rotation → meme mania), with a smaller repeat of
   the identical signature in Jan 2023.
4. All seven sleeves bled simultaneously — common-factor, not
   sleeve-specific.
5. Outside the window the signal is strong: +146% trough→end,
   2022 +48%, 2026 +21%, composite IC +0.055 (t +3.4).

**But three honest caveats before anyone calls it "fixable":**

a. **The full-sample return leans on an unshortable book.** 30% of the
   short leg is sub-$5; real borrow costs for distressed microcaps dwarf
   the modeled 10 bps. Both the +7.3%/yr *and* the −36.6% are understated
   in magnitude terms — reality is worse on both ends.
b. **In-sample weights.** Sleeve weights were chosen after seeing the lab
   on this same sample. The 2022 +48% and 2026 +21% are not out-of-sample
   for the weighting choice.
c. **One sample, one regime window (2020–2026).** We have exactly one
   major junk-squeeze episode and one minor echo. "Regime conditioning"
   tuned on n=1 is curve-fitting with extra steps.

**What would actually address it** (in rough priority order):

1. **Borrow-cost realism** — model hard-to-borrow haircuts on the short
   book (or a price ≥ $5 / borrowability filter as the *main* spec, not a
   sensitivity; the ≥$5 run kept Sharpe 0.49 with DD −33.8%).
2. **Regime guard on the short book** — cut or hedge Q1 exposure when
   speculative-breadth proxies spike (unprofitable-tech momentum, retail
   flow, meme-basket velocity). The failure signature (Q1 ripping while
   Q5 flat, Q1–Q5 corr → 1) is *detectable in real time*.
3. **Reframe the product** — the quintile profile (Q1 −8.2%, Q5 +0.5%,
   Q3/Q4 best) already says the edge is Q1-*avoidance*, not Q5 selection.
   A long-only "hold Q2–Q5" or Q1-exclusion overlay sidesteps the entire
   short-squeeze problem at the cost of the short-side premium.
4. **Event-driven rewrite (v2)** — the monthly grid can't express any of
   the above; realistic frictions and intra-month risk control need the
   event stream.

Bottom line: the signal is real but it has a known, recurring,
identifiable failure mode — short junk in speculative melt-ups. That is
fixable in principle (borrow realism + a short-book regime guard), but
any fix tuned on this single episode should be treated as guilty until
proven innocent out-of-sample.
