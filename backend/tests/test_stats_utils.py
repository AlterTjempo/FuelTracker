import random

from services.stats_utils import (
    bootstrap_ci,
    bootstrap_diff_ci,
    brier_score,
    diebold_mariano,
    haversine_km,
    least_squares_slope,
    pinball_loss,
    reliability_table,
    theil_sen,
)


def test_theil_sen_ignores_an_outlier_but_least_squares_does_not():
    xs = [0, 1, 2, 3, 4, 5]
    ys = [0.0, 1.0, 2.0, 3.0, 40.0, 5.0]  # one wild point, true slope 1
    assert abs(theil_sen(xs, ys) - 1.0) < 1e-9
    assert least_squares_slope(ys) > 3


def test_bootstrap_ci_contains_the_mean_and_is_seeded():
    rng = random.Random(1)
    data = [rng.gauss(2.0, 1.0) for _ in range(300)]
    lo, hi = bootstrap_ci(data, n=500, seed=3)
    assert lo < sum(data) / len(data) < hi
    assert (lo, hi) == bootstrap_ci(data, n=500, seed=3)
    assert bootstrap_ci([1.0]) is None


def test_bootstrap_diff_ci_excludes_zero_for_a_real_difference():
    rng = random.Random(2)
    a = [rng.gauss(1.0, 1.0) for _ in range(200)]
    b = [rng.gauss(0.0, 1.0) for _ in range(200)]
    lo, hi = bootstrap_diff_ci(a, b, n=500)
    assert lo > 0


def test_diebold_mariano_detects_a_better_model_and_not_a_tie():
    rng = random.Random(4)
    base = [abs(rng.gauss(0, 2.0)) for _ in range(200)]
    better = [x * 0.6 for x in base]
    stat, p = diebold_mariano(better, base)
    assert stat < 0 and p < 0.01
    same = [x + rng.gauss(0, 0.05) for x in base]
    _, p_tie = diebold_mariano(same, base)
    assert p_tie > 0.1
    assert diebold_mariano(better[:10], base[:10]) is None  # too short to test


def test_pinball_and_brier():
    assert pinball_loss(10, 8, 0.9) == 0.9 * 2
    assert pinball_loss(8, 10, 0.9) == (0.9 - 1) * -2
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert brier_score([0.5, 0.5], [1, 0]) == 0.25


def test_reliability_table_bins_predictions():
    rows = reliability_table([0.1, 0.1, 0.9, 0.9], [0, 0, 1, 1], bins=5)
    assert [r["n"] for r in rows] == [2, 2]
    assert rows[0]["observed"] == 0 and rows[1]["observed"] == 1


def test_haversine_known_distance():
    # Kleve to Nijmegen is roughly 25 km
    d = haversine_km(51.79, 6.14, 51.84, 5.86)
    assert 18 < d < 25
    assert haversine_km(51.0, 6.0, 51.0, 6.0) == 0
