// outlier.hpp — ゲーティング (tag-design.md §4 ③)
// leave-one-out (最悪残差の除外) は pipeline 側で solve2d を再呼び出しして行う。
#pragma once

#include <cmath>

#include "geometry.hpp"

namespace rtls_solver {

// 予測位置からあり得ない距離を棄却する。true = 通過 (採用)。
inline bool gate(const Vec2& anchor, real range_m, const Vec2& predicted, real v_max_ms,
                 real dt_s, real margin_m) {
    const real dx = anchor.x - predicted.x, dy = anchor.y - predicted.y;
    const real predicted_range = std::sqrt(dx * dx + dy * dy);
    return std::fabs(range_m - predicted_range) <= v_max_ms * dt_s + margin_m;
}

}  // namespace rtls_solver
