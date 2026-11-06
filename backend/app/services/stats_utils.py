"""Small statistics helpers shared by the backtests (pure Python, no numpy)."""

import math
import random
from statistics import mean, median
from typing import Callable, Optional, Sequence


def bootstrap_ci(
    values: Sequence[float],
    stat: Callable[[Sequence[float]], float] = mean,
    n: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Optional[tuple[float, float]]:
    """Percentile bootstrap confidence interval of `stat`."""
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    k = len(values)
    stats = sorted(stat(rng.choices(values, k=k)) for _ in range(n))
    return stats[int(n * alpha / 2)], stats[min(n - 1, int(n * (1 - alpha / 2)))]


def bootstrap_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    n: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Optional[tuple[float, float]]:
    """CI of mean(a) - mean(b) from independent resamples."""
    if len(a) < 2 or len(b) < 2:
        return None
    rng = random.Random(seed)
    diffs = sorted(
        mean(rng.choices(a, k=len(a))) - mean(rng.choices(b, k=len(b)))
        for _ in range(n)
    )
    return diffs[int(n * alpha / 2)], diffs[min(n - 1, int(n * (1 - alpha / 2)))]


def theil_sen(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Median of all pairwise slopes: robust against single outliers."""
    slopes = [
        (ys[j] - ys[i]) / (xs[j] - xs[i])
        for i in range(len(xs))
        for j in range(i + 1, len(xs))
        if xs[j] != xs[i]
    ]
    return median(slopes) if slopes else None


def least_squares_slope(ys: Sequence[float]) -> Optional[float]:
    """Slope per step of y against 0, 1, 2, ... (the original Go Now trend)."""
    n = len(ys)
    if n < 2:
        return None
    xm, ym = (n - 1) / 2.0, mean(ys)
    den = sum((i - xm) ** 2 for i in range(n))
    return sum((i - xm) * (y - ym) for i, y in enumerate(ys)) / den if den else None


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def diebold_mariano(
    loss_model: Sequence[float], loss_base: Sequence[float], h: int = 1
) -> Optional[tuple[float, float]]:
    """One-sided Diebold-Mariano test that the model has LOWER expected loss.

    Returns (statistic, p_value). Small p = model better. Uses a Newey-West
    variance with h-1 lags (overlapping h-step forecast errors are correlated),
    the Harvey-Leybourne-Newbold small-sample correction and a normal
    approximation (fine for n >= ~25; below that None is returned).
    """
    n = len(loss_model)
    if n != len(loss_base) or n < 25:
        return None
    d = [a - b for a, b in zip(loss_model, loss_base)]
    dm = mean(d)
    var = sum((x - dm) ** 2 for x in d) / n
    for lag in range(1, max(1, h)):
        cov = sum((d[i] - dm) * (d[i - lag] - dm) for i in range(lag, n)) / n
        var += 2 * (1 - lag / h) * cov
    if var <= 0:
        return None
    stat = dm / math.sqrt(var / n)
    corr = math.sqrt(max(1e-9, (n + 1 - 2 * h + h * (h - 1) / n) / n))
    stat *= corr
    return stat, normal_cdf(stat)


def pinball_loss(y: float, q_pred: float, tau: float) -> float:
    diff = y - q_pred
    return tau * diff if diff >= 0 else (tau - 1) * diff


def brier_score(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)


def reliability_table(
    probs: Sequence[float], outcomes: Sequence[int], bins: int = 5
) -> list[dict]:
    """Predicted probability vs. observed frequency per probability bin."""
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [
            i
            for i, p in enumerate(probs)
            if (lo <= p < hi) or (b == bins - 1 and p == 1.0)
        ]
        if idx:
            rows.append(
                {
                    "bin": f"{lo:.1f}-{hi:.1f}",
                    "n": len(idx),
                    "mean_predicted": mean(probs[i] for i in idx),
                    "observed": mean(outcomes[i] for i in idx),
                }
            )
    return rows


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
