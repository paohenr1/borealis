"""Markdown report builder for the factor correlation + PCA analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _fmt(x, digits=3):
    if x is None:
        return "n/a"
    try:
        if np.isnan(x):
            return "n/a"
    except TypeError:
        return str(x)
    return f"{x:.{digits}f}"


def _corr_table(corr: pd.DataFrame) -> list[str]:
    cols = list(corr.columns)
    L = ["| factor | " + " | ".join(cols) + " |",
         "|---|" + "|".join("---" for _ in cols) + "|"]
    for c in cols:
        L.append("| " + c + " | " +
                 " | ".join(_fmt(corr.loc[c, d], 2) for d in cols) + " |")
    return L


def _describe_pc(loadings: pd.DataFrame, pc: str, top_n: int = 3) -> str:
    s = loadings[pc].sort_values(key=np.abs, ascending=False)
    pos = [f for f in s.head(2 * top_n).index if s[f] > 0][:top_n]
    neg = [f for f in s.head(2 * top_n).index if s[f] < 0][:top_n]
    bits = []
    if pos:
        bits.append("loads positively on " +
                    ", ".join(f"{f} ({s[f]:+.2f})" for f in pos))
    if neg:
        bits.append("negatively on " +
                    ", ".join(f"{f} ({s[f]:+.2f})" for f in neg))
    return "; ".join(bits) + "."


def build_corrpca_report(corr: pd.DataFrame, pairs: pd.DataFrame,
                         pca_res: dict, effdim: dict, clusters: list[dict],
                         meta: dict) -> str:
    L = []
    L.append("# Borealis Factor Structure: Correlation + PCA")
    L.append("")
    L.append(f"_Generated {meta['generated']} · panel {meta['panel']} · "
             f"{meta['n_dates']} monthly rebalance dates "
             f"({meta['date_min']} → {meta['date_max']})_")
    L.append("")
    L.append("## Sampling scheme")
    for line in meta["scheme"]:
        L.append(f"- {line}")
    L.append("")
    L.append("## Mean cross-sectional correlation matrix (Fisher-z averaged)")
    L.append("")
    L += _corr_table(corr)
    L.append("")
    L.append("## Most correlated pairs")
    L.append("")
    L.append("| factor A | factor B | corr |")
    L.append("|---|---|---|")
    for _, r in pairs.head(10).iterrows():
        L.append(f"| {r['factor_a']} | {r['factor_b']} | {_fmt(r['corr'], 3)} |")
    L.append("")
    L.append("## Least correlated pairs (|corr| smallest)")
    L.append("")
    L.append("| factor A | factor B | corr |")
    L.append("|---|---|---|")
    for _, r in pairs.tail(10).iloc[::-1].iterrows():
        L.append(f"| {r['factor_a']} | {r['factor_b']} | {_fmt(r['corr'], 3)} |")
    L.append("")
    L.append("## PCA eigenvalues (on the date-averaged correlation matrix)")
    L.append("")
    L.append("| PC | eigenvalue | explained | cumulative |")
    L.append("|---|---|---|---|")
    for i, (v, e, c) in enumerate(zip(pca_res["eigenvalues"],
                                      pca_res["explained"],
                                      pca_res["cumulative"])):
        L.append(f"| PC{i+1} | {_fmt(v, 3)} | {_fmt(e*100, 1)}% | {_fmt(c*100, 1)}% |")
    L.append("")
    L.append(f"Effective dimensionality: **{effdim['kaiser_gt1']}** components "
             f"with eigenvalue > 1 (Kaiser); **{effdim['n_pc_80pct']}** PCs for "
             f"80% of variance, **{effdim['n_pc_90pct']}** for 90%.")
    L.append("")
    L.append("## Component interpretations (top loadings)")
    L.append("")
    loadings = pca_res["loadings"]
    n_show = min(5, loadings.shape[1])
    for i in range(n_show):
        pc = f"PC{i+1}"
        var = pca_res["explained"][i] * 100
        L.append(f"**{pc}** ({var:.1f}% of variance): {_describe_pc(loadings, pc)}")
    L.append("")
    L.append("## Loadings, first 5 PCs")
    L.append("")
    show = loadings.iloc[:, :n_show]
    L.append("| factor | " + " | ".join(show.columns) + " |")
    L.append("|---|" + "|".join("---" for _ in show.columns) + "|")
    for f in show.index:
        L.append("| " + f + " | " +
                 " | ".join(_fmt(show.loc[f, c], 2) for c in show.columns) + " |")
    L.append("")
    L.append("## Redundancy clusters (|corr| ≥ 0.70)")
    L.append("")
    if clusters:
        for c in clusters:
            L.append(f"- **{', '.join(c['members'])}** — max |corr| "
                     f"{c['max_abs_corr']:.2f}; keep **{c['keep']}**, "
                     f"drop/merge {', '.join(c['drop'])}.")
    else:
        L.append("No factor pairs breach the 0.70 |corr| threshold.")
    L.append("")
    L.append("## Key takeaways")
    for line in corrpca_takeaways(pairs, pca_res, effdim, clusters):
        L.append(f"- {line}")
    L.append("")
    L.append("## Caveats")
    for line in meta["caveats"]:
        L.append(f"- {line}")
    L.append("")
    return "\n".join(L)


def corrpca_takeaways(pairs: pd.DataFrame, pca_res: dict, effdim: dict,
                      clusters: list[dict]) -> list[str]:
    lines = []
    top = pairs.iloc[0]
    lines.append(f"Highest factor overlap: {top['factor_a']} × {top['factor_b']} "
                 f"(corr {top['corr']:+.3f}) — these two carry almost the same "
                 f"information and should not both earn full weight.")
    n = len(pca_res["factors"])
    lines.append(f"Of {n} factors, {effdim['kaiser_gt1']} principal components "
                 f"exceed eigenvalue 1 and {effdim['n_pc_80pct']} explain 80% "
                 f"of the variance: the effective dimensionality of the "
                 f"factor set is roughly {effdim['n_pc_80pct']}, not {n}.")
    if clusters:
        dropped = sorted({d for c in clusters for d in c["drop"]})
        lines.append("Redundancy recommendation: consolidate "
                     f"{len(dropped)} near-duplicate factors "
                     f"({', '.join(dropped)}) into their cluster keepers "
                     "before assigning composite weights — otherwise the "
                     "composite double-counts the same underlying exposure.")
    else:
        lines.append("No near-duplicate pairs at the 0.70 threshold; the "
                     "composite's diversification across factors is genuine.")
    pc1_var = pca_res["explained"][0] * 100
    lines.append(f"PC1 alone explains {pc1_var:.1f}% of factor variance — "
                 "check its interpretation above: if it is a quality axis, "
                 "the composite's quality sleeve is implicitly overweight "
                 "through factor multiplicity, not through its stated weight.")
    return lines
