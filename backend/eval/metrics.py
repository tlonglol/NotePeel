"""Retrieval metrics. Pure functions, no I/O, unit-tested in tests/backend/test_metrics.py.

Conventions:
  * A "hit" is decided by the caller via `is_relevant(item)`; this module never
    looks inside retrieved objects.
  * Recall is macro-averaged per question. A question with no relevant targets
    (unanswerable) is excluded from recall/MRR by returning None.
  * Percentiles use the nearest-rank method on the raw sample, no interpolation,
    so p99 over 250 samples is literally the 248th value, not a smoothed guess.
"""
from __future__ import annotations

import math
import random
from typing import Callable, Iterable, List, Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")


def coverage_at_k(
    ranked: Sequence[T],
    targets: Sequence[object],
    k: int,
    covers: Callable[[T, object], bool],
) -> Optional[float]:
    """Fraction of `targets` that at least one of the top-k `ranked` items covers."""
    if not targets:
        return None
    top = list(ranked[:k])
    hit = sum(1 for t in targets if any(covers(r, t) for r in top))
    return hit / len(targets)


def reciprocal_rank(
    ranked: Sequence[T],
    targets: Sequence[object],
    k: int,
    covers: Callable[[T, object], bool],
) -> Optional[float]:
    """1 / rank of the first item (within top-k) that covers any target; 0 if none."""
    if not targets:
        return None
    for i, r in enumerate(ranked[:k]):
        if any(covers(r, t) for t in targets):
            return 1.0 / (i + 1)
    return 0.0


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    """Nearest-rank percentile. p in [0, 100]."""
    if not values:
        return None
    s = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(s)))
    return s[rank - 1]


def bootstrap_ci(
    values: Sequence[float],
    iters: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Optional[Tuple[float, float]]:
    """Percentile bootstrap CI of the mean. Deterministic for a given seed."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    rng = random.Random(seed)
    n = len(vals)
    means: List[float] = []
    for _ in range(iters):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[max(0, math.floor(alpha / 2 * iters) - 1)]
    hi = means[min(iters - 1, math.ceil((1 - alpha / 2) * iters) - 1)]
    return lo, hi
