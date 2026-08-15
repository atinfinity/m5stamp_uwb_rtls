// geometry.hpp — 高低差補正・最小二乗測位 (tag-design.md §4 ②④⑤)
// Arduino 非依存・ヘッダオンリー。Python 実装 (server/positioning/geometry.py) と
// 同一仕様。リファインは scipy soft_l1 相当の IRLS Gauss-Newton。
#pragma once

#include <cmath>
#include <cstdint>

namespace rtls_solver {

// ESP32-C5 の FPU は単精度。一致試験で精度不足が出た場合のみ double へ切替える。
using real = float;

constexpr int kMaxRanges = 8;

struct Vec2 {
    real x;
    real y;
};

struct SolveResult {
    real x = 0;
    real y = 0;
    real residuals[kMaxRanges] = {};
    int n = 0;
    real rms = 0;
    bool ok = false;
};

// 斜距離 → 水平距離。根号内が負なら false (棄却)。
inline bool horizontalRange(real slant_m, real dz_m, real* out) {
    const real v = slant_m * slant_m - dz_m * dz_m;
    if (v < 0) {
        return false;
    }
    *out = std::sqrt(v);
    return true;
}

namespace detail {

// アンカー配置の縮退 (共線) 判定: 座標共分散 (ddof=1) の最小固有値 < 1e-6
inline bool degenerate(const Vec2* a, int n) {
    real mx = 0, my = 0;
    for (int i = 0; i < n; i++) {
        mx += a[i].x;
        my += a[i].y;
    }
    mx /= n;
    my /= n;
    real cxx = 0, cxy = 0, cyy = 0;
    for (int i = 0; i < n; i++) {
        const real dx = a[i].x - mx, dy = a[i].y - my;
        cxx += dx * dx;
        cxy += dx * dy;
        cyy += dy * dy;
    }
    cxx /= (n - 1);
    cxy /= (n - 1);
    cyy /= (n - 1);
    const real half = (cxx + cyy) / 2;
    const real root = std::sqrt((cxx - cyy) * (cxx - cyy) / 4 + cxy * cxy);
    return (half - root) < real(1e-6);
}

// 線形化 LSQ 初期解: 重心を原点に平行移動して桁落ちを防ぎ、
// (n-1) 本の線形方程式の正規方程式 (2×2) を手解きする。
inline bool linearInit(const Vec2* a, const real* r, int n, real* ox, real* oy) {
    real mx = 0, my = 0;
    for (int i = 0; i < n; i++) {
        mx += a[i].x;
        my += a[i].y;
    }
    mx /= n;
    my /= n;

    real ata00 = 0, ata01 = 0, ata11 = 0, atb0 = 0, atb1 = 0;
    const real x0 = a[0].x - mx, y0 = a[0].y - my;
    for (int i = 1; i < n; i++) {
        const real xi = a[i].x - mx, yi = a[i].y - my;
        const real ax = 2 * (xi - x0);
        const real ay = 2 * (yi - y0);
        const real b = (xi * xi - x0 * x0) + (yi * yi - y0 * y0) + (r[0] * r[0] - r[i] * r[i]);
        ata00 += ax * ax;
        ata01 += ax * ay;
        ata11 += ay * ay;
        atb0 += ax * b;
        atb1 += ay * b;
    }
    const real det = ata00 * ata11 - ata01 * ata01;
    if (std::fabs(det) < real(1e-9)) {
        return false;
    }
    *ox = (ata11 * atb0 - ata01 * atb1) / det + mx;
    *oy = (ata00 * atb1 - ata01 * atb0) / det + my;
    return true;
}

}  // namespace detail

// 距離セットから 2D 座標を解く。3 距離未満・縮退配置は ok=false。
// 線形化 LSQ 初期解 → soft_l1 重みの IRLS Gauss-Newton (f_scale=0.3, 最大 10 反復)。
// ステップ発散 (>1 m) 時はその時点の解を採用する (tag-design.md §4 ⑤)。
inline SolveResult solve2d(const Vec2* anchors, const real* ranges, int n) {
    SolveResult res;
    if (n < 3 || n > kMaxRanges || detail::degenerate(anchors, n)) {
        return res;
    }
    real x, y;
    if (!detail::linearInit(anchors, ranges, n, &x, &y)) {
        return res;
    }

    constexpr real kFScale = real(0.3);
    for (int iter = 0; iter < 10; iter++) {
        real jtj00 = 0, jtj01 = 0, jtj11 = 0, jtf0 = 0, jtf1 = 0;
        for (int i = 0; i < n; i++) {
            const real dx = x - anchors[i].x, dy = y - anchors[i].y;
            real d = std::sqrt(dx * dx + dy * dy);
            if (d < real(1e-6)) {
                d = real(1e-6);
            }
            const real f = d - ranges[i];
            const real z = (f / kFScale) * (f / kFScale);
            const real w = 1 / std::sqrt(1 + z);  // soft_l1: ρ'(z) = 1/√(1+z)
            const real jx = dx / d, jy = dy / d;
            jtj00 += w * jx * jx;
            jtj01 += w * jx * jy;
            jtj11 += w * jy * jy;
            jtf0 += w * jx * f;
            jtf1 += w * jy * f;
        }
        const real det = jtj00 * jtj11 - jtj01 * jtj01;
        if (std::fabs(det) < real(1e-12)) {
            break;
        }
        const real sx = -(jtj11 * jtf0 - jtj01 * jtf1) / det;
        const real sy = -(jtj00 * jtf1 - jtj01 * jtf0) / det;
        const real step = std::sqrt(sx * sx + sy * sy);
        if (step > 1) {
            break;  // 発散ガード: 直前の解を採用
        }
        x += sx;
        y += sy;
        if (step < real(1e-4)) {
            break;
        }
    }

    real sumsq = 0;
    for (int i = 0; i < n; i++) {
        const real dx = x - anchors[i].x, dy = y - anchors[i].y;
        const real f = std::sqrt(dx * dx + dy * dy) - ranges[i];
        res.residuals[i] = f;
        sumsq += f * f;
    }
    res.x = x;
    res.y = y;
    res.n = n;
    res.rms = std::sqrt(sumsq / n);
    res.ok = true;
    return res;
}

}  // namespace rtls_solver
