"""experiment/stats.py must be right before any result is reported with it."""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiment"))
import stats  # noqa: E402


def test_wilson_matches_textbook_values():
    lo, hi = stats.wilson(10, 10)
    assert abs(lo - 0.7225) < 1e-4 and hi == pytest.approx(1.0)
    lo, hi = stats.wilson(0, 10)
    assert lo == 0.0 and abs(hi - 0.2775) < 1e-4
    lo, hi = stats.wilson(5, 10)
    assert abs(lo - 0.2366) < 1e-4 and abs(hi - 0.7634) < 1e-4


def test_fisher_matches_textbook_values():
    assert stats.fisher_exact(3, 1, 1, 3) == pytest.approx(0.485714, abs=1e-6)     # Fisher's tea-tasting table
    assert stats.fisher_exact(10, 0, 3, 7) == pytest.approx(0.0030960, abs=1e-6)
    assert stats.fisher_exact(5, 5, 5, 5) == pytest.approx(1.0)


def test_fisher_agrees_with_scipy_on_random_tables():
    scipy_stats = pytest.importorskip("scipy.stats")
    rng = random.Random(1)
    for _ in range(200):
        t = [rng.randint(0, 30) for _ in range(4)]
        if sum(t) == 0:
            continue
        ours = stats.fisher_exact(*t)
        theirs = scipy_stats.fisher_exact([[t[0], t[1]], [t[2], t[3]]], alternative="two-sided")[1]
        assert ours == pytest.approx(theirs, rel=1e-6, abs=1e-12), t


def test_exact_power_agrees_with_simulation():
    p1, n1, p2, n2 = 0.8, 20, 0.4, 20
    exact = stats.power_two_proportions(p1, n1, p2, n2)
    rng = random.Random(2)
    hits = 0
    trials = 4000
    for _ in range(trials):
        k1 = sum(rng.random() < p1 for _ in range(n1))
        k2 = sum(rng.random() < p2 for _ in range(n2))
        hits += stats.fisher_exact(k1, n1 - k1, k2, n2 - k2) < 0.05
    assert abs(hits / trials - exact) < 0.03, (hits / trials, exact)


def test_power_is_alpha_bounded_under_the_null_and_grows_with_n():
    assert stats.power_two_proportions(0.5, 30, 0.5, 30) <= 0.05
    assert stats.power_two_proportions(0.8, 30, 0.4, 30) > stats.power_two_proportions(0.8, 10, 0.4, 10)


def test_invalid_inputs_are_refused():
    with pytest.raises(ValueError):
        stats.wilson(1, 0)
    with pytest.raises(ValueError):
        stats.wilson(11, 10)
