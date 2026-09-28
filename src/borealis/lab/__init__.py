"""Factor-efficacy lab: information coefficients, quintile spreads, signal half-life.

All analyses run on the point-in-time panel (see ``borealis.ingest.panel``):
factor values at date *t* are always paired with forward returns *after* *t*,
so no lookahead is introduced here.
"""
from borealis.lab import halflife, ic, preprocess, quintiles, report, run

__all__ = ["halflife", "ic", "preprocess", "quintiles", "report", "run"]
