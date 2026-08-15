// rtls_solver のホストネイティブテスト (server-design.md §13-1 と同一ケース)。
// 実行: ./firmware/test_native/run.sh
#include <cassert>
#include <cmath>
#include <cstdio>

#include "geometry.hpp"
#include "pipeline.hpp"

using namespace rtls_solver;

static const AnchorInfo kAnchors[4] = {
    {0x0010, 0, 0, real(2.2), 0},
    {0x0011, 25, 0, real(2.2), 0},
    {0x0013, 0, 25, real(2.2), 0},
    {0x0014, 25, 25, real(2.2), 0},
};
static constexpr real kTagH = real(1.0);

// 疑似乱数 (deterministic LCG) — 一様 [0,1)
static uint32_t lcg_state = 12345;
static real frand() {
    lcg_state = lcg_state * 1664525u + 1013904223u;
    return real(lcg_state >> 8) / real(1 << 24);
}
static real gauss(real sigma) {  // Box-Muller
    real u1 = frand() + real(1e-9), u2 = frand();
    return sigma * std::sqrt(-2 * std::log(u1)) * std::cos(real(2 * M_PI) * u2);
}

static int32_t slantMm(const AnchorInfo& a, real x, real y, real extra_m = 0) {
    const real dx = a.x - x, dy = a.y - y, dz = a.z - kTagH;
    const real d = std::sqrt(dx * dx + dy * dy + dz * dz) + extra_m;
    return int32_t(d * 1000 + real(0.5));
}

static void test_solve_exact() {
    Vec2 pts[4];
    real rr[4];
    for (int i = 0; i < 4; i++) {
        pts[i] = {kAnchors[i].x, kAnchors[i].y};
        const real dx = kAnchors[i].x - 10, dy = kAnchors[i].y - real(7.5);
        rr[i] = std::sqrt(dx * dx + dy * dy);
    }
    SolveResult s = solve2d(pts, rr, 4);
    assert(s.ok);
    assert(std::fabs(s.x - 10) < real(1e-3));
    assert(std::fabs(s.y - real(7.5)) < real(1e-3));
    assert(s.rms < real(1e-3));
}

static void test_solve_collinear() {
    Vec2 pts[3] = {{0, 0}, {10, 0}, {20, 0}};
    real rr[3] = {5, 5, 15};
    assert(!solve2d(pts, rr, 3).ok);
    assert(!solve2d(pts, rr, 2).ok);
}

static void test_solve_noisy_median() {
    real errs[200];
    for (int t = 0; t < 200; t++) {
        const real x = 2 + frand() * 21, y = 2 + frand() * 21;
        Vec2 pts[4];
        real rr[4];
        for (int i = 0; i < 4; i++) {
            pts[i] = {kAnchors[i].x, kAnchors[i].y};
            const real dx = kAnchors[i].x - x, dy = kAnchors[i].y - y;
            rr[i] = std::sqrt(dx * dx + dy * dy) + gauss(real(0.05));
        }
        SolveResult s = solve2d(pts, rr, 4);
        assert(s.ok);
        errs[t] = std::sqrt((s.x - x) * (s.x - x) + (s.y - y) * (s.y - y));
    }
    // 中央値 < 10 cm (σ=5cm 入力) — 挿入ソートで中央値
    for (int i = 1; i < 200; i++) {
        real v = errs[i];
        int j = i - 1;
        while (j >= 0 && errs[j] > v) {
            errs[j + 1] = errs[j];
            j--;
        }
        errs[j + 1] = v;
    }
    assert(errs[100] < real(0.10));
}

static PosOut feedEpoch(TagPipeline& pl, uint32_t seq, uint64_t t_ms, real x, real y,
                        int nlos_idx = -1, real nlos_m = 0, int drop_idx = -1) {
    RangeMeas m[4];
    for (int i = 0; i < 4; i++) {
        m[i].anchor = kAnchors[i].addr;
        if (i == drop_idx) {
            m[i] = {kAnchors[i].addr, 0, false};
        } else {
            m[i] = {kAnchors[i].addr, slantMm(kAnchors[i], x, y, i == nlos_idx ? nlos_m : 0),
                    true};
        }
    }
    return pl.process(seq, t_ms, t_ms + 20, m, 4);
}

static void test_pipeline_tracking() {
    TagPipeline pl(kAnchors, 4, kTagH);
    PosOut out;
    for (int i = 0; i < 10; i++) {
        out = feedEpoch(pl, i + 1, 1000 + i * 500, 10, 8);
    }
    assert(out.valid && out.state == TrackState::TRACKING);
    assert(std::hypot(out.x - 10, out.y - 8) < real(0.05));
}

static void test_pipeline_nlos_removed() {
    TagPipeline pl(kAnchors, 4, kTagH);
    for (int i = 0; i < 5; i++) {
        feedEpoch(pl, i + 1, 1000 + i * 500, 10, 8);
    }
    PosOut out = feedEpoch(pl, 6, 4000, 10, 8, /*nlos_idx=*/0, /*nlos_m=*/2);
    assert(out.valid && out.state == TrackState::TRACKING);
    assert(out.n_used == 3);  // 汚染距離が除外されている
    assert(std::hypot(out.x - 10, out.y - 8) < real(0.30));
}

static void test_pipeline_coasting_and_dup() {
    TagPipeline pl(kAnchors, 4, kTagH);
    for (int i = 0; i < 5; i++) {
        feedEpoch(pl, i + 1, 1000 + i * 500, 10, 8);
    }
    // 2 距離欠測 → COASTING
    RangeMeas m[4] = {{0x0010, 0, false},
                      {0x0011, 0, false},
                      {0x0013, slantMm(kAnchors[2], 10, 8), true},
                      {0x0014, slantMm(kAnchors[3], 10, 8), true}};
    PosOut out = pl.process(6, 4000, 4020, m, 4);
    assert(out.valid && out.state == TrackState::COASTING && out.n_used == 0);
    // 同一 seq は破棄
    assert(!pl.process(6, 4500, 4520, m, 4).valid);
    // 鮮度切れは破棄
    assert(!pl.process(7, 5000, 5000 + 10000, m, 4).valid);
}

static void test_pipeline_lost_reacquire() {
    TagPipeline pl(kAnchors, 4, kTagH);
    for (int i = 0; i < 3; i++) {
        feedEpoch(pl, i + 1, 1000 + i * 500, 10, 8);
    }
    PosOut out = feedEpoch(pl, 10, 30000, 20, 20);  // lost_sec 超え → 再初期化
    assert(out.valid && out.state == TrackState::TRACKING);
    assert(std::hypot(out.x - 20, out.y - 20) < real(0.1));
}

static void test_pipeline_reboot_seq_reset() {
    TagPipeline pl(kAnchors, 4, kTagH);
    for (int i = 0; i < 5; i++) {
        feedEpoch(pl, 100 + i, 1000 + i * 500, 10, 8);
    }
    // 6 秒後に seq=1 で再開 (タグ再起動) → 受理され追尾が続く
    PosOut out = feedEpoch(pl, 1, 10000, 11, 8);
    assert(out.valid);
    assert(std::hypot(out.x - 11, out.y - 8) < real(0.5));
    // 直後の seq 逆行 (同一 t_ms 帯) は従来どおり破棄
    assert(!feedEpoch(pl, 1, 10500, 11, 8).valid);
}

int main() {
    test_solve_exact();
    test_solve_collinear();
    test_solve_noisy_median();
    test_pipeline_tracking();
    test_pipeline_nlos_removed();
    test_pipeline_coasting_and_dup();
    test_pipeline_lost_reacquire();
    test_pipeline_reboot_seq_reset();
    printf("all rtls_solver tests passed\n");
    return 0;
}
