"""Markdown report builder for the factor-efficacy lab."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _fmt(x, digits=4):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{digits}f}"


def _fmt_pct(x, digits=2):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100*x:.{digits}f}%"


def _half_life_cell(hl: dict) -> str:
    if hl["days"] is None:
        return "n/a"
    d = hl["days"]
    if hl["censored"] == "below-threshold-at-first-lag":
        return f"<{d:.0f}"
    if hl["censored"] and hl["censored"].startswith("above-"):
        return f">{d:.0f}"
    return f"{d:.0f}"


def build_report(results: dict, meta: dict) -> str:
    """Assemble the full Markdown report.

    results: {factor: {"ic_21": {...}, "ic_63": {...}, "qspread_21": {...},
                       "qspread_63": {...}, "half_life": {...},
                       "decay": {lag: rho}, "annual_21": {year: spread}}}
    meta: sampling scheme, dates, universe stats, caveats.
    """
    L = []
    L.append("# Borealis Factor-Efficacy Lab")
    L.append("")
    L.append(f"_Generated {meta['generated']} · panel {meta['panel']} · "
             f"{meta['n_dates']} monthly rebalance dates "
             f"({meta['date_min']} → {meta['date_max']})_")
    L.append("")
    L.append("## Sampling scheme")
    for line in meta["scheme"]:
        L.append(f"- {line}")
    L.append("")
    L.append("## Information coefficients (rank IC, sector-neutral z vs forward total return)")
    L.append("")
    L.append("| factor | IC₂₁ mean | IC₂₁ t-stat | IC₂₁ hit rate | IC₆₃ mean | IC₆₃ t-stat | IC₆₃ hit rate | N |")
    L.append("|---|---|---|---|---|---|---|---|")
    for f, r in results.items():
        a, b = r["ic_21"], r["ic_63"]
        L.append(f"| {f} | {_fmt(a['mean'])} | {_fmt(a['tstat'], 2)} | {_fmt_pct(a['hit_rate'])} "
                 f"| {_fmt(b['mean'])} | {_fmt(b['tstat'], 2)} | {_fmt_pct(b['hit_rate'])} | {a['n']} |")
    L.append("")
    L.append("## Quintile spreads (Q5 − Q1, equal-weighted, monthly %)")
    L.append("")
    L.append("| factor | spread₂₁ mean | spread₂₁ t-stat | spread₂₁ hit rate | Q1₂₁ | Q5₂₁ | "
             "spread₆₃ mean | spread₆₃ t-stat | cumulative₂₁ |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for f, r in results.items():
        a, b = r["qspread_21"], r["qspread_63"]
        L.append(f"| {f} | {_fmt_pct(a['mean'])} | {_fmt(a['tstat'], 2)} | {_fmt_pct(a['hit_rate'])} "
                 f"| {_fmt_pct(a['q1_mean'])} | {_fmt_pct(a['q5_mean'])} "
                 f"| {_fmt_pct(b['mean'])} | {_fmt(b['tstat'], 2)} | {_fmt_pct(a['cumulative'], 1)} |")
    L.append("")
    L.append("## Signal half-life (trading days; rank autocorrelation decay to 0.5)")
    L.append("")
    L.append("| factor | half-life (d) | " +
             " | ".join(f"L{lag}" for lag in meta["lags"]) + " |")
    L.append("|---|---|" + "|".join("---" for _ in meta["lags"]) + "|")
    for f, r in results.items():
        cells = [_fmt(r["decay"].get(lag), 2) for lag in meta["lags"]]
        L.append(f"| {f} | {_half_life_cell(r['half_life'])} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("## Annual quintile spreads, 21-day horizon (monthly %)")
    L.append("")
    years = sorted({y for r in results.values() for y in r["annual_21"]})
    L.append("| factor | " + " | ".join(str(y) for y in years) + " |")
    L.append("|---|" + "|".join("---" for _ in years) + "|")
    for f, r in results.items():
        L.append(f"| {f} | " + " | ".join(_fmt_pct(r["annual_21"].get(y)) for y in years) + " |")
    L.append("")
    L.append("## Key takeaways")
    for line in takeaways(results):
        L.append(f"- {line}")
    L.append("")
    L.append("## Caveats")
    for line in meta["caveats"]:
        L.append(f"- {line}")
    L.append("")
    return "\n".join(L)


def _hl_str(hl: dict) -> str:
    if hl["days"] is None or np.isnan(hl["days"]):
        return "n/a"
    d = f"{hl['days']:.0f}d"
    if hl["censored"] == "below-threshold-at-first-lag":
        return f"<{d}"
    if hl["censored"] and hl["censored"].startswith("above-"):
        return f">{d}"
    return f"~{d}"


def takeaways(results: dict) -> list[str]:
    """Auto-generated highlights: strongest/weakest factors by IC t-stat."""
    rows = [(f, r["ic_21"]["tstat"], r["ic_21"]["mean"],
             r["qspread_21"]["mean"], r["half_life"])
            for f, r in results.items()]
    rows = [x for x in rows if not np.isnan(x[1])]
    if not rows:
        return ["No factor produced a computable IC series."]
    by_t = sorted(rows, key=lambda x: x[1], reverse=True)
    lines = []
    top = by_t[:3]
    lines.append("Strongest signals (by 21-day IC t-stat): " +
                 "; ".join(f"{f} (t={t:.2f}, IC={m:+.4f}, Q5−Q1={s:+.2%}/mo, "
                           f"half-life≈{_hl_str(h)})"
                           for f, t, m, s, h in top) + ".")
    weak = [x for x in by_t if abs(x[1]) < 2.0]
    if weak:
        lines.append("Indistinguishable from noise (|t| < 2): " +
                     ", ".join(f for f, *_ in weak[:5]) +
                     (" …" if len(weak) > 5 else "") + ".")
    neg = [x for x in by_t if x[1] < -2.0]
    if neg:
        lines.append("Significantly *negative* IC (signal runs opposite to "
                     "its orientation — consider flipping or dropping): " +
                     ", ".join(f for f, *_ in neg) + ".")
    def _hl_days(hl):
        d = hl["days"]
        return d if d and not np.isnan(d) else -1
    slow = sorted(rows, key=lambda x: _hl_days(x[4]), reverse=True)[:2]
    if slow:
        lines.append("Slowest-decaying signals (rebalance least often): " +
                     ", ".join(f"{f} ({_hl_str(h)})" for f, _, _, _, h in slow) + ".")
    return lines
