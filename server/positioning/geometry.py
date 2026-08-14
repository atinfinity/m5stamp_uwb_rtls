"""高低差補正・最小二乗測位 (server-design.md §5 ②④⑤)。"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares


def horizontal_range_m(slant_m: float, dz_m: float) -> float | None:
    """斜距離を水平距離へ変換。根号内が負なら None(棄却)。"""
    v = slant_m * slant_m - dz_m * dz_m
    if v < 0:
        return None
    return math.sqrt(v)


@dataclass(frozen=True)
class SolveResult:
    x: float
    y: float
    residuals: tuple[float, ...]  # 使用距離ごとの残差 [m] (‖p−a‖ − r)
    rms_residual: float
    converged: bool


def _linear_init(px: np.ndarray, py: np.ndarray, r: np.ndarray) -> tuple[float, float]:
    """線形化 LSQ 初期解。桁落ち防止のためアンカー重心を原点に平行移動して解く。"""
    cx, cy = float(px.mean()), float(py.mean())
    x, y = px - cx, py - cy
    a = np.column_stack([2.0 * (x[1:] - x[0]), 2.0 * (y[1:] - y[0])])
    b = (x[1:] ** 2 - x[0] ** 2) + (y[1:] ** 2 - y[0] ** 2) + (r[0] ** 2 - r[1:] ** 2)
    sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    return float(sol[0]) + cx, float(sol[1]) + cy


def solve_2d(anchors_xy: list[tuple[float, float]], ranges_m: list[float]) -> SolveResult | None:
    """距離セットから 2D 座標を解く。3 距離未満・縮退配置は None。

    線形化 LSQ で初期解を求め、soft_l1 損失の非線形リファインで仕上げる。
    リファインが収束しない場合は線形解を採用し converged=False を返す。
    """
    n = len(ranges_m)
    if n < 3 or n != len(anchors_xy):
        return None
    px = np.array([a[0] for a in anchors_xy])
    py = np.array([a[1] for a in anchors_xy])
    r = np.array(ranges_m, dtype=float)

    # 縮退(共線)チェック: アンカー座標の分散行列の最小固有値で判定
    pts = np.column_stack([px, py])
    cov = np.cov(pts.T)
    if np.linalg.eigvalsh(cov)[0] < 1e-6:
        return None

    x0, y0 = _linear_init(px, py, r)

    def residual_fn(p: np.ndarray) -> np.ndarray:
        return np.hypot(px - p[0], py - p[1]) - r

    try:
        fit = least_squares(residual_fn, x0=[x0, y0], loss="soft_l1", f_scale=0.3, max_nfev=50)
        x, y = float(fit.x[0]), float(fit.x[1])
        converged = bool(fit.success)
    except Exception:
        x, y, converged = x0, y0, False

    res = residual_fn(np.array([x, y]))
    rms = float(np.sqrt(np.mean(res**2)))
    return SolveResult(x=x, y=y, residuals=tuple(float(v) for v in res),
                       rms_residual=rms, converged=converged)
