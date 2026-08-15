// kalman.hpp — 等速モデル 2D カルマン (tag-design.md §4 ⑦)
// 状態 [x, y, vx, vy]。4×4 固定サイズをベタ書き、行列ライブラリ不使用。
// Python 実装 (server/positioning/kalman.py) と同一の式。
#pragma once

#include <cmath>

#include "geometry.hpp"

namespace rtls_solver {

class CvKalman2D {
public:
    explicit CvKalman2D(real sigma_a) : sigma_a2_(sigma_a * sigma_a) {}

    bool initialized() const { return initialized_; }

    void reset() { initialized_ = false; }

    void init(real x, real y, real sigma_m) {
        x_[0] = x;
        x_[1] = y;
        x_[2] = 0;
        x_[3] = 0;
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 4; j++) {
                p_[i][j] = 0;
            }
        }
        p_[0][0] = sigma_m * sigma_m;
        p_[1][1] = sigma_m * sigma_m;
        p_[2][2] = 4;  // 初期速度は未知: 大きめの分散
        p_[3][3] = 4;
        initialized_ = true;
    }

    void predict(real dt_s) {
        const real dt = dt_s > real(1e-3) ? dt_s : real(1e-3);
        // x = F x
        x_[0] += dt * x_[2];
        x_[1] += dt * x_[3];
        // P = F P Fᵀ + Q  (F = [[I, dt·I],[0, I]] の構造を利用)
        // 位置-速度ブロックごとに展開: 軸 0 は (0,2)、軸 1 は (1,3)
        real np[4][4];
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 4; j++) {
                real v = p_[i][j];
                if (i < 2) v += dt * p_[i + 2][j];          // 行方向: F P
                np[i][j] = v;
            }
        }
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 2; j++) {
                np[i][j] += dt * np[i][j + 2];              // 列方向: (F P) Fᵀ
            }
        }
        const real d2 = dt * dt;
        const real d3 = d2 * dt / 2;
        const real d4 = d2 * d2 / 4;
        np[0][0] += sigma_a2_ * d4;
        np[0][2] += sigma_a2_ * d3;
        np[2][0] += sigma_a2_ * d3;
        np[2][2] += sigma_a2_ * d2;
        np[1][1] += sigma_a2_ * d4;
        np[1][3] += sigma_a2_ * d3;
        np[3][1] += sigma_a2_ * d3;
        np[3][3] += sigma_a2_ * d2;
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 4; j++) {
                p_[i][j] = np[i][j];
            }
        }
    }

    void update(real zx, real zy, real sigma_m) {
        const real r = sigma_m * sigma_m;
        // S = H P Hᵀ + R (H は先頭 2 状態の選択)
        const real s00 = p_[0][0] + r, s01 = p_[0][1];
        const real s10 = p_[1][0], s11 = p_[1][1] + r;
        const real det = s00 * s11 - s01 * s10;
        if (std::fabs(det) < real(1e-12)) {
            return;
        }
        const real i00 = s11 / det, i01 = -s01 / det;
        const real i10 = -s10 / det, i11 = s00 / det;
        // K = P Hᵀ S⁻¹ (4×2)
        real k[4][2];
        for (int i = 0; i < 4; i++) {
            k[i][0] = p_[i][0] * i00 + p_[i][1] * i10;
            k[i][1] = p_[i][0] * i01 + p_[i][1] * i11;
        }
        const real y0 = zx - x_[0], y1 = zy - x_[1];
        for (int i = 0; i < 4; i++) {
            x_[i] += k[i][0] * y0 + k[i][1] * y1;
        }
        // P = (I − K H) P = P − K · P[0:2][:]
        real np[4][4];
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 4; j++) {
                np[i][j] = p_[i][j] - (k[i][0] * p_[0][j] + k[i][1] * p_[1][j]);
            }
        }
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 4; j++) {
                p_[i][j] = np[i][j];
            }
        }
    }

    void state(real* x, real* y, real* vx, real* vy) const {
        *x = x_[0];
        *y = x_[1];
        *vx = x_[2];
        *vy = x_[3];
    }

private:
    real sigma_a2_;
    real x_[4] = {};
    real p_[4][4] = {};
    bool initialized_ = false;
};

}  // namespace rtls_solver
