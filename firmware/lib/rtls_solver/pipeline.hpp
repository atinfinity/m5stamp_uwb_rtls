// pipeline.hpp — タグ上解算パイプライン (tag-design.md §4)
// Python 実装 (server/positioning/pipeline.py) と同一の処理段・状態機械。
// Arduino 非依存: 入出力は素の構造体のみ。
#pragma once

#include <cstdint>

#include "geometry.hpp"
#include "kalman.hpp"
#include "outlier.hpp"

namespace rtls_solver {

struct Tuning {  // server/config.yaml の tuning と同一の既定値
    real max_age_ms = 500;
    real v_max_ms = real(2.0);
    real gate_margin_m = real(0.6);
    real residual_gate_m = real(0.5);
    real sigma_a = real(1.0);
    real sigma_m_floor = real(0.15);
    real stale_sec = real(2.0);
    real lost_sec = real(10.0);
};

struct AnchorInfo {
    uint16_t addr;
    real x, y, z;
    int32_t bias_mm;
};

struct RangeMeas {
    uint16_t anchor;
    int32_t d_mm;
    bool ok;
};

enum class TrackState : uint8_t { INIT, TRACKING, COASTING, STALE, LOST };

struct PosOut {
    bool valid = false;  // false = 破棄 (重複 seq / 鮮度切れ / 未初期化欠測)
    uint64_t t_ms = 0;
    real x = 0, y = 0, vx = 0, vy = 0;
    int n_used = 0;
    real rms = 0;
    TrackState state = TrackState::INIT;
};

constexpr int kMaxAnchorTable = 16;
// seq が逆行していても t_ms がこれ以上新しければタグ再起動とみなして受理する
constexpr uint64_t kRebootGapMs = 5000;

class TagPipeline {
public:
    TagPipeline(const AnchorInfo* anchors, int n_anchors, real tag_height_m,
                const Tuning& tuning = Tuning())
        : tuning_(tuning), tag_height_(tag_height_m), kf_(tuning.sigma_a) {
        n_table_ = n_anchors < kMaxAnchorTable ? n_anchors : kMaxAnchorTable;
        for (int i = 0; i < n_table_; i++) {
            table_[i] = anchors[i];
        }
    }

    PosOut process(uint32_t seq, uint64_t t_ms, uint64_t recv_ms, const RangeMeas* meas,
                   int n_meas) {
        PosOut out;
        // ① 検証。seq 逆行はタグ再起動 (t_ms が kRebootGapMs 以上新しい) なら受理する。
        if (has_seq_ && seq <= last_seq_ &&
            (!has_t_ || t_ms - last_t_ms_ < kRebootGapMs)) {
            return out;
        }
        if (recv_ms > t_ms && real(recv_ms - t_ms) > tuning_.max_age_ms) {
            return out;
        }
        last_seq_ = seq;
        has_seq_ = true;

        real dt_s = 0;
        if (has_t_) {
            dt_s = real(t_ms - last_t_ms_) / 1000;
            if (dt_s < real(1e-3)) dt_s = real(1e-3);
        }

        // LOST 判定: 長時間空いたらフィルタを作り直す
        if (has_success_ && real(t_ms - last_success_ms_) / 1000 > tuning_.lost_sec) {
            kf_.reset();
            has_success_ = false;
        }
        last_t_ms_ = t_ms;
        has_t_ = true;

        // ②③ 補正とゲーティング
        Vec2 pts[kMaxRanges];
        real rr[kMaxRanges];
        int n = usableRanges(meas, n_meas, dt_s, pts, rr);

        if (n < 3) {
            return coast(out, t_ms, dt_s);
        }

        // ④⑤⑥ 解算と外れ値除去
        int n_used = n;
        SolveResult sol = solveWithRejection(pts, rr, n, &n_used);
        if (!sol.ok) {
            return coast(out, t_ms, dt_s);
        }

        // ⑦ カルマン
        real sigma_m = sol.rms > tuning_.sigma_m_floor ? sol.rms : tuning_.sigma_m_floor;
        if (!kf_.initialized()) {
            kf_.init(sol.x, sol.y, sigma_m);
        } else {
            kf_.predict(dt_s);
            kf_.update(sol.x, sol.y, sigma_m);
        }
        has_success_ = true;
        last_success_ms_ = t_ms;

        out.valid = true;
        out.t_ms = t_ms;
        kf_.state(&out.x, &out.y, &out.vx, &out.vy);
        out.n_used = n_used;
        out.rms = sol.rms;
        out.state = TrackState::TRACKING;
        return out;
    }

private:
    int usableRanges(const RangeMeas* meas, int n_meas, real dt_s, Vec2* pts, real* rr) {
        bool have_pred = kf_.initialized();
        Vec2 pred{};
        if (have_pred) {
            real vx, vy;
            kf_.state(&pred.x, &pred.y, &vx, &vy);
        }
        int n = 0;
        for (int i = 0; i < n_meas && n < kMaxRanges; i++) {
            if (!meas[i].ok) continue;
            const AnchorInfo* a = findAnchor(meas[i].anchor);
            if (a == nullptr) continue;
            const real slant = real(meas[i].d_mm - a->bias_mm) / 1000;
            real h;
            if (!horizontalRange(slant, a->z - tag_height_, &h)) continue;
            if (have_pred &&
                !gate({a->x, a->y}, h, pred, tuning_.v_max_ms, dt_s, tuning_.gate_margin_m)) {
                continue;
            }
            pts[n] = {a->x, a->y};
            rr[n] = h;
            n++;
        }
        return n;
    }

    SolveResult solveWithRejection(const Vec2* pts, const real* rr, int n, int* n_used) {
        SolveResult sol = solve2d(pts, rr, n);
        *n_used = n;
        if (!sol.ok) return sol;
        int worst = 0;
        for (int i = 1; i < n; i++) {
            if (std::fabs(sol.residuals[i]) > std::fabs(sol.residuals[worst])) worst = i;
        }
        if (std::fabs(sol.residuals[worst]) > tuning_.residual_gate_m && n >= 4) {
            Vec2 p2[kMaxRanges];
            real r2[kMaxRanges];
            int m = 0;
            for (int i = 0; i < n; i++) {
                if (i == worst) continue;
                p2[m] = pts[i];
                r2[m] = rr[i];
                m++;
            }
            SolveResult sol2 = solve2d(p2, r2, m);
            if (sol2.ok && sol2.rms < sol.rms) {
                *n_used = m;
                return sol2;
            }
        }
        return sol;
    }

    PosOut coast(PosOut& out, uint64_t t_ms, real dt_s) {
        // 欠測エポック: 予測のみ (COASTING)。フィルタ未初期化なら何も出せない。
        if (!kf_.initialized()) {
            return out;
        }
        kf_.predict(dt_s);
        out.valid = true;
        out.t_ms = t_ms;
        kf_.state(&out.x, &out.y, &out.vx, &out.vy);
        out.n_used = 0;
        out.rms = 0;
        out.state = stalenessState(t_ms);
        return out;
    }

    TrackState stalenessState(uint64_t t_ms) const {
        if (!has_success_) {
            return TrackState::COASTING;
        }
        const real gap_s = real(t_ms - last_success_ms_) / 1000;
        if (gap_s > tuning_.lost_sec) return TrackState::LOST;
        if (gap_s > tuning_.stale_sec) return TrackState::STALE;
        return TrackState::COASTING;
    }

    const AnchorInfo* findAnchor(uint16_t addr) const {
        for (int i = 0; i < n_table_; i++) {
            if (table_[i].addr == addr) return &table_[i];
        }
        return nullptr;
    }

    Tuning tuning_;
    real tag_height_;
    CvKalman2D kf_;
    AnchorInfo table_[kMaxAnchorTable];
    int n_table_ = 0;
    uint32_t last_seq_ = 0;
    bool has_seq_ = false;
    uint64_t last_t_ms_ = 0;
    bool has_t_ = false;
    uint64_t last_success_ms_ = 0;
    bool has_success_ = false;
};

}  // namespace rtls_solver
