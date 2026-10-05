"""Statistics for the pre-registered study (stdlib only, exact where it matters).

    wilson(k, n)                 95% Wilson score interval for a proportion
    fisher_exact(a, b, c, d)     two-sided Fisher exact p-value for the 2x2 table [[a, b], [c, d]]
    power_two_proportions(...)   exact power of the two-sided Fisher test at alpha, by enumeration
    min_detectable_gap(...)      smallest gap p_strong - p_cheap detectable with the given power

Why exact: with n = 20-30 per arm, normal approximations misstate both p-values and power.
"""
from math import comb, sqrt


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple:
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= k <= n:
        raise ValueError("k must be in [0, n]")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _hypergeom_pmf(x: int, row1: int, col1: int, total: int) -> float:
    return comb(col1, x) * comb(total - col1, row1 - x) / comb(total, row1)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided p: sum of probabilities of tables (same margins) no more likely than the observed one."""
    row1, col1, total = a + b, a + c, a + b + c + d
    lo, hi = max(0, row1 - (total - col1)), min(row1, col1)
    p_obs = _hypergeom_pmf(a, row1, col1, total)
    eps = 1e-12 * p_obs
    return min(1.0, sum(p for p in (_hypergeom_pmf(x, row1, col1, total) for x in range(lo, hi + 1))
                        if p <= p_obs + eps))


def _binom(k: int, n: int, p: float) -> float:
    return comb(n, k) * p ** k * (1 - p) ** (n - k)


def power_two_proportions(p1: float, n1: int, p2: float, n2: int, alpha: float = 0.05) -> float:
    """P(two-sided Fisher p < alpha) when arm 1 succeeds with p1 over n1 trials and arm 2 with p2 over n2."""
    reject = {}
    total = 0.0
    for k1 in range(n1 + 1):
        w1 = _binom(k1, n1, p1)
        if w1 < 1e-15:
            continue
        for k2 in range(n2 + 1):
            w2 = _binom(k2, n2, p2)
            if w2 < 1e-15:
                continue
            key = (k1, k2)
            if key not in reject:
                reject[key] = fisher_exact(k1, n1 - k1, k2, n2 - k2) < alpha
            if reject[key]:
                total += w1 * w2
    return total


def min_detectable_gap(p_base: float, n1: int, n2: int, power: float = 0.8, alpha: float = 0.05,
                       step: float = 0.01) -> float:
    """Smallest d such that p_base + d (arm 1) vs p_base (arm 2) is detected with >= power. 1.0 if none."""
    d = step
    while p_base + d <= 1.0 + 1e-9:
        if power_two_proportions(min(1.0, p_base + d), n1, p_base, n2, alpha) >= power:
            return round(d, 4)
        d += step
    return 1.0


def describe(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.0%} (95% CI {lo:.0%}-{hi:.0%})"


if __name__ == "__main__":
    print("Wilson 10/10:", describe(10, 10))
    print("Fisher 10/10 vs 3/10:", round(fisher_exact(10, 0, 3, 7), 4))
    for base in (0.2, 0.4, 0.6):
        print(f"n=30 v 30, base {base:.0%}: minimum detectable gap at 80% power =",
              min_detectable_gap(base, 30, 30))
