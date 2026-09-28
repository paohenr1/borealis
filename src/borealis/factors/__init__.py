"""Factor library. Each module exposes a `<name>_score(df) -> pd.Series`
oriented so HIGHER = more attractive."""
from borealis.factors import value, quality, growth, momentum, lowvol

__all__ = ["value", "quality", "growth", "momentum", "lowvol"]
