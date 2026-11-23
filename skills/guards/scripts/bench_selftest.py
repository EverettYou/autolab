#!/usr/bin/env python3
"""Microbenchmark self-test — class E / six-green-checks instrument guard.

The failure this prevents (``labs/2026-08-04-layered-scatter-gpu-cost/REPORT.md``): a 5.18×
measurement of which **3.20× was the harness** re-gathering loop-invariant tensors inside the
timed region, written into a knowledge doc before anyone checked.

Rule (``wiki/techniques/claim-hygiene-checklist.md`` class E):
  time the *same* work two ways and require the ratio not to move beyond a tolerance.

Usage from a lab microbenchmark::

    from pathlib import Path
    import importlib.util
    p = Path("<repo root>/skills/guards/scripts/bench_selftest.py")
    spec = importlib.util.spec_from_file_location("bench_selftest", p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    mod.assert_timing_ratio_stable(fn_hoisted, fn_naive, max_ratio=1.15)
    # or: mod.require_known_cost(fn, expected_s=0.01, tol=0.5)

Run this file directly to execute its own fixture self-test (must exit 0).
"""
from __future__ import annotations

import time
from typing import Callable


def _time_call(fn: Callable[[], None], *, warmup: int, reps: int) -> float:
    for _ in range(warmup):
        fn()
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t0) / reps


def assert_timing_ratio_stable(
    fn_a: Callable[[], None],
    fn_b: Callable[[], None],
    *,
    max_ratio: float = 1.15,
    warmup: int = 3,
    reps: int = 20,
    label_a: str = "a",
    label_b: str = "b",
) -> float:
    """Time ``fn_a`` and ``fn_b``; raise ``AssertionError`` if ``max(ta,tb)/min > max_ratio``.

    Both callables must perform the *same* billed work. Use this after hoisting
    loop-invariant gathers: if the ratio still moves, the instrument is measuring
    something other than the work you named.
    """
    if max_ratio < 1.0:
        raise ValueError("max_ratio must be >= 1.0")
    ta = _time_call(fn_a, warmup=warmup, reps=reps)
    tb = _time_call(fn_b, warmup=warmup, reps=reps)
    lo, hi = (ta, tb) if ta <= tb else (tb, ta)
    ratio = hi / lo if lo > 0 else float("inf")
    if ratio > max_ratio:
        raise AssertionError(
            f"bench_selftest: timing ratio {ratio:.3f} exceeds max_ratio={max_ratio} "
            f"({label_a}={ta*1e3:.3f} ms, {label_b}={tb*1e3:.3f} ms). "
            f"The two arms are not measuring the same work — hoist loop-invariants "
            f"or fix the harness before publishing a ratio."
        )
    return ratio


def require_known_cost(
    fn: Callable[[], None],
    *,
    expected_s: float,
    tol: float = 0.5,
    warmup: int = 2,
    reps: int = 10,
) -> float:
    """Time ``fn`` against a known-cost fixture; raise if relative error exceeds ``tol``.

    ``tol=0.5`` means measured may be within 50% of ``expected_s``. This is the
    instrument-validating-itself case: the reference must be independent of the
    benchmark under test (e.g. ``time.sleep``, fixed ``numpy`` work), not the
    benchmark's own earlier output.
    """
    if expected_s <= 0:
        raise ValueError("expected_s must be positive")
    measured = _time_call(fn, warmup=warmup, reps=reps)
    rel = abs(measured - expected_s) / expected_s
    if rel > tol:
        raise AssertionError(
            f"bench_selftest: known-cost fixture drifted — measured {measured*1e3:.3f} ms, "
            f"expected {expected_s*1e3:.3f} ms (rel err {rel:.2%} > tol {tol:.0%}). "
            f"Clock or environment is not a trustworthy instrument right now."
        )
    return measured


def _fixture_selftest() -> None:
    """Built-in check: hoisting-sensitive timing must fail loudly; identical arms must pass."""
    import numpy as np

    n, k = 4096, 64
    src = np.random.randn(n, k)
    idx = np.arange(0, n, 17)

    def naive():
        # Re-gather every "round" — the 2026-08-04 harness bug shape.
        acc = 0.0
        for _ in range(30):
            view = src[idx]  # allocates
            acc += float(view.sum())
        return acc

    def hoisted():
        view = src[idx]  # once
        acc = 0.0
        for _ in range(30):
            acc += float(view.sum())
        return acc

    # Same work, two ways after hoisting both: must be stable.
    def hoisted_a():
        view = src[idx]
        return float(view.sum())

    def hoisted_b():
        view = src[idx].copy()
        return float(view.sum())

    assert_timing_ratio_stable(hoisted_a, hoisted_b, max_ratio=2.0, warmup=5, reps=50)

    # Known-cost fixture: sleep is independent of the benchmark.
    require_known_cost(lambda: time.sleep(0.01), expected_s=0.01, tol=0.8, warmup=1, reps=3)

    # Negative control: naive vs hoisted on a large enough gather must exceed a tight ratio.
    # (If this *doesn't* raise, the fixture isn't discriminating — fail the self-test.)
    try:
        assert_timing_ratio_stable(
            hoisted, naive, max_ratio=1.05, warmup=2, reps=8, label_a="hoisted", label_b="naive"
        )
    except AssertionError:
        pass  # expected — instrument caught the hoist bug
    else:
        raise AssertionError(
            "bench_selftest fixture failed to discriminate hoisted vs naive; "
            "increase work or lower max_ratio before trusting this helper"
        )

    print("bench_selftest: fixture OK (stable arms pass; hoist bug fails loudly; known-cost ok)")


if __name__ == "__main__":
    _fixture_selftest()
