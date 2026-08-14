import math
import random

from server.positioning import geometry


ANCHORS = [(0.0, 0.0), (25.0, 0.0), (0.0, 25.0), (25.0, 25.0)]


def true_ranges(x, y, anchors=ANCHORS):
    return [math.hypot(ax - x, ay - y) for ax, ay in anchors]


def test_exact_solution():
    sol = geometry.solve_2d(ANCHORS, true_ranges(10.0, 7.5))
    assert sol is not None
    assert abs(sol.x - 10.0) < 1e-6
    assert abs(sol.y - 7.5) < 1e-6
    assert sol.rms_residual < 1e-6


def test_noisy_solution_within_cm():
    rng = random.Random(1)
    errs = []
    for _ in range(200):
        x, y = rng.uniform(2, 23), rng.uniform(2, 23)
        r = [d + rng.gauss(0, 0.05) for d in true_ranges(x, y)]
        sol = geometry.solve_2d(ANCHORS, r)
        assert sol is not None
        errs.append(math.hypot(sol.x - x, sol.y - y))
    errs.sort()
    assert errs[len(errs) // 2] < 0.10  # 中央値 10 cm 未満 (σ=5cm 入力)


def test_three_ranges_minimum():
    sol = geometry.solve_2d(ANCHORS[:3], true_ranges(10.0, 7.5, ANCHORS[:3]))
    assert sol is not None
    assert abs(sol.x - 10.0) < 1e-6


def test_collinear_returns_none():
    collinear = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    assert geometry.solve_2d(collinear, true_ranges(5.0, 5.0, collinear)) is None


def test_too_few_returns_none():
    assert geometry.solve_2d(ANCHORS[:2], [1.0, 2.0]) is None


def test_horizontal_range():
    assert abs(geometry.horizontal_range_m(5.0, 1.2) - math.sqrt(25 - 1.44)) < 1e-9
    assert geometry.horizontal_range_m(1.0, 1.2) is None  # 根号内負 → 棄却
