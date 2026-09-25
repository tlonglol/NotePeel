from eval.metrics import coverage_at_k, reciprocal_rank, percentile, bootstrap_ci, mean

eq = lambda r, t: r == t  # noqa: E731


def test_coverage_counts_each_target_once():
    assert coverage_at_k(["a", "b", "a"], ["a", "c"], k=3, covers=eq) == 0.5
    assert coverage_at_k(["a", "b"], ["a", "b"], k=1, covers=eq) == 0.5
    assert coverage_at_k([], ["a"], k=5, covers=eq) == 0.0


def test_coverage_none_for_no_targets():
    assert coverage_at_k(["a"], [], k=5, covers=eq) is None


def test_reciprocal_rank():
    assert reciprocal_rank(["x", "y", "a"], ["a"], k=10, covers=eq) == 1 / 3
    assert reciprocal_rank(["x", "y", "a"], ["a"], k=2, covers=eq) == 0.0
    assert reciprocal_rank(["a"], [], k=2, covers=eq) is None


def test_percentile_nearest_rank():
    vals = list(range(1, 101))
    assert percentile(vals, 50) == 50
    assert percentile(vals, 99) == 99
    assert percentile(vals, 100) == 100
    assert percentile([7], 99) == 7
    assert percentile([], 50) is None


def test_bootstrap_ci_deterministic_and_bracketing():
    vals = [0.0, 1.0] * 50
    lo, hi = bootstrap_ci(vals, iters=500, seed=1)
    assert lo <= 0.5 <= hi
    assert bootstrap_ci(vals, iters=500, seed=1) == (lo, hi)
    assert bootstrap_ci([], iters=10) is None


def test_mean_skips_none():
    assert mean([1.0, None, 3.0]) == 2.0
    assert mean([None]) is None
