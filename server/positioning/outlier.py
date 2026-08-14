"""ゲーティング (server-design.md §5 ③)。

leave-one-out(最悪残差の除外)は pipeline 側で solve_2d を再呼び出しして行う。
"""
from __future__ import annotations

import math


def gate(
    anchor_xy: tuple[float, float],
    range_m: float,
    predicted_xy: tuple[float, float],
    v_max_ms: float,
    dt_s: float,
    margin_m: float,
) -> bool:
    """予測位置からあり得ない距離を棄却する。True = 通過(採用)。"""
    predicted_range = math.hypot(anchor_xy[0] - predicted_xy[0], anchor_xy[1] - predicted_xy[1])
    return abs(range_m - predicted_range) <= v_max_ms * dt_s + margin_m
