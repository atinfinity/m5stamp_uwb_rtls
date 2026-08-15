// rtls_config_msg.h のホストネイティブテスト (Issue #28)。
// canonical JSON は tools/publish_config.py の出力形式と一致させてある。
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>

#include "rtls_config_msg.h"

using namespace rtls;

static const char* kAnchorsJson =
    "{\"version\":7,\"tag_height_m\":1.0,"
    "\"anchors\":{"
    "\"0x0010\":{\"x\":0.0,\"y\":0.0,\"z\":2.2,\"bias_mm\":-35},"
    "\"0x0011\":{\"x\":25.0,\"y\":0.0,\"z\":2.2,\"bias_mm\":12},"
    "\"0x0013\":{\"x\":0.0,\"y\":25.0,\"z\":2.2,\"bias_mm\":0},"
    "\"0x0014\":{\"x\":25.0,\"y\":25.0,\"z\":2.2,\"bias_mm\":0}},"
    "\"cells\":{"
    "\"A\":{\"rect\":[0,0,25,25],\"anchors\":[\"0x0010\",\"0x0011\",\"0x0013\",\"0x0014\"]},"
    "\"B\":{\"rect\":[25,0,50,25],\"anchors\":[\"0x0011\",\"0x0013\",\"0x0014\"]}}}";

static void test_parse_anchors_config() {
    char buf[1024];
    strcpy(buf, kAnchorsJson);
    stripJsonSpaces(buf);
    AnchorsConfig cfg;
    assert(parseAnchorsConfig(buf, &cfg));
    assert(cfg.version == 7);
    assert(std::fabs(cfg.tag_height_m - 1.0f) < 1e-6f);
    assert(cfg.n_anchors == 4);
    assert(cfg.anchors[0].addr == 0x0010 && cfg.anchors[0].bias_mm == -35);
    assert(cfg.anchors[1].addr == 0x0011 && std::fabs(cfg.anchors[1].x - 25.0f) < 1e-6f);
    assert(cfg.n_cells == 2);
    assert(strcmp(cfg.cells[0].name, "A") == 0);
    assert(cfg.cells[0].n_anchors == 4 && cfg.cells[0].anchors[0] == 0x0010);
    assert(strcmp(cfg.cells[1].name, "B") == 0);
    assert(cfg.cells[1].n_anchors == 3);
    assert(std::fabs(cfg.cells[1].rect[0] - 25.0f) < 1e-6f);
}

static void test_parse_rejects_bad_config() {
    AnchorsConfig cfg;
    assert(!parseAnchorsConfig("{\"tag_height_m\":1.0}", &cfg));  // version 無し
    // 2 台しかないセルは拒否 (解算不可)
    char bad[512];
    strcpy(bad,
           "{\"version\":1,\"anchors\":{\"0x0010\":{\"x\":0,\"y\":0,\"z\":2,\"bias_mm\":0}},"
           "\"cells\":{\"A\":{\"rect\":[0,0,10,10],\"anchors\":[\"0x0010\",\"0x0011\"]}}}");
    assert(!parseAnchorsConfig(bad, &cfg));
}

static void test_parse_tuning() {
    char buf[256];
    strcpy(buf, "{\"version\":9,\"v_max_ms\":3.0,\"residual_gate_m\":0.7}");
    TuningDef t;
    uint32_t ver = 0;
    assert(parseTuningConfig(buf, &t, &ver));
    assert(ver == 9);
    assert(std::fabs(t.v_max_ms - 3.0f) < 1e-6f);
    assert(std::fabs(t.residual_gate_m - 0.7f) < 1e-6f);
    assert(std::fabs(t.sigma_a - 1.0f) < 1e-6f);  // 未指定キーは既定値のまま
    assert(!parseTuningConfig("{\"v_max_ms\":3.0}", &t, &ver));  // version 必須
}

static void test_select_cell_hysteresis() {
    char buf[1024];
    strcpy(buf, kAnchorsJson);
    stripJsonSpaces(buf);
    AnchorsConfig cfg;
    assert(parseAnchorsConfig(buf, &cfg));
    const float margin = 2.0f;
    assert(selectCell(cfg.cells, cfg.n_cells, 5, 5, -1, margin) == 0);    // A
    assert(selectCell(cfg.cells, cfg.n_cells, 40, 5, -1, margin) == 1);   // B
    // ヒステリシス: A 保持のまま境界 +2m 以内は A に留まる
    assert(selectCell(cfg.cells, cfg.n_cells, 26.0f, 10, 0, margin) == 0);
    assert(selectCell(cfg.cells, cfg.n_cells, 28.0f, 10, 0, margin) == 1);
    // どのセルにも入らない座標は最近傍セル
    assert(selectCell(cfg.cells, cfg.n_cells, 5, 49, -1, margin) == 0);
}

static void test_uart_frame() {
    uint8_t f[kUartFrameLen];
    buildUartFrame(f, 0x01, 1, 0x11223344u, 12.5f, 8.25f, 0.5f, -0.25f, 0.08f, 4);
    assert(f[0] == 0xB5 && f[1] == 0x50);
    assert(f[2] == 0x01 && f[3] == 1);
    uint32_t t;
    memcpy(&t, &f[4], 4);
    assert(t == 0x11223344u);
    float x;
    memcpy(&x, &f[8], 4);
    assert(std::fabs(x - 12.5f) < 1e-6f);
    assert(f[28] == 4);
    uint8_t sum = 0;
    for (size_t i = 0; i < kUartFrameLen - 1; i++) sum ^= f[i];
    assert(f[29] == sum);
}

static void test_position_json() {
    char buf[256];
    size_t n = buildPositionJson(buf, sizeof(buf), 0x0001, 1755212345690ULL, 12.34f,
                                 8.76f, 0.51f, -0.12f, 4, 0.03f, "TRACKING", "A");
    assert(n > 0);
    assert(strstr(buf, "\"tag\":\"0x0001\"") != nullptr);
    assert(strstr(buf, "\"state\":\"TRACKING\"") != nullptr);
    assert(strstr(buf, "\"src\":\"tag\"") != nullptr);
    assert(strstr(buf, "\"n_anchors\":4") != nullptr);
    char small[32];
    assert(buildPositionJson(small, sizeof(small), 1, 0, 0, 0, 0, 0, 0, 0, "X", "") == 0);
}

int main() {
    test_parse_anchors_config();
    test_parse_rejects_bad_config();
    test_parse_tuning();
    test_select_cell_hysteresis();
    test_uart_frame();
    test_position_json();
    printf("all rtls_config tests passed\n");
    return 0;
}
