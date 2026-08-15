// rtls_common のホストネイティブテスト (実機不要)。
// 実行: ./firmware/test_native/run.sh  (CI でも同スクリプトを使用)
#include <cassert>
#include <cstdio>
#include <cstring>

#include "rtls_msg.h"
#include "rtls_slots.h"

using namespace rtls;

static void test_slot_index() {
    assert(slotIndexForTag(0x0001, 0x0001) == 0);
    assert(slotIndexForTag(0x0005, 0x0001) == 4);
}

static void test_in_slot_windows() {
    // スロット 0: [0, 90) が有効、[90, 100) はガード
    assert(inSlot(0, 0));
    assert(inSlot(89, 0));
    assert(!inSlot(90, 0));
    assert(!inSlot(99, 0));
    // スロット 1: [100, 190)
    assert(!inSlot(99, 1));
    assert(inSlot(100, 1));
    assert(inSlot(189, 1));
    assert(!inSlot(190, 1));
    // スーパーフレーム跨ぎ: 500ms 後も同じ窓
    assert(inSlot(500 + 42, 0));
    assert(!inSlot(500 + 95, 0));
    // スロット 4: [400, 490)
    assert(inSlot(450, 4));
    assert(!inSlot(495, 4));
}

static void test_slot_exclusive() {
    // 任意の時刻で有効なのは高々 1 スロット
    for (uint64_t t = 0; t < 1000; t++) {
        int active = 0;
        for (int s = 0; s < 5; s++) {
            if (inSlot(t, s)) active++;
        }
        assert(active <= 1);
    }
}

static void test_ms_until_slot() {
    assert(msUntilSlot(0, 0) == 0);       // 今スロット内
    assert(msUntilSlot(95, 0) == 405);    // ガード中 → 次フレームの先頭まで
    assert(msUntilSlot(0, 1) == 100);
    assert(msUntilSlot(250, 1) == 350);   // 過ぎた → 次フレーム
    assert(msUntilSlot(399, 4) == 1);
}

static void test_superframe_index() {
    assert(superframeIndex(0) == 0);
    assert(superframeIndex(499) == 0);
    assert(superframeIndex(500) == 1);
}

static void test_build_ranges_json() {
    RangeEntry e[3] = {
        {0x0010, 5234, true},
        {0x0011, 0, false},
        {0x0013, 12000, true},
    };
    char buf[512];
    size_t n = buildRangesJson(buf, sizeof(buf), 0x0001, 42, 1755212345678ULL, e, 3);
    assert(n > 0);
    const char* expected =
        "{\"tag\":\"0x0001\",\"seq\":42,\"t_ms\":1755212345678,\"ranges\":["
        "{\"a\":\"0x0010\",\"d_mm\":5234,\"ok\":true},"
        "{\"a\":\"0x0011\",\"d_mm\":0,\"ok\":false},"
        "{\"a\":\"0x0013\",\"d_mm\":12000,\"ok\":true}]}";
    assert(strcmp(buf, expected) == 0);

    // バッファ不足は 0 を返す (途中で切れた JSON を出さない)
    char small[32];
    assert(buildRangesJson(small, sizeof(small), 0x0001, 42, 0, e, 3) == 0);
}

static void test_parse_anchors_json() {
    uint16_t out[8];
    size_t n = parseAnchorsJson(
        "{\"cell\":\"B\",\"anchors\":[\"0x0011\",\"0x0012\",\"0x0014\",\"0x0015\"]}",
        out, 8);
    assert(n == 4);
    assert(out[0] == 0x0011 && out[1] == 0x0012 && out[2] == 0x0014 && out[3] == 0x0015);

    // max_out で打ち切り
    assert(parseAnchorsJson("{\"anchors\":[\"0x0011\",\"0x0012\"]}", out, 1) == 1);
    // anchors キーが無ければ 0
    assert(parseAnchorsJson("{\"cell\":\"A\"}", out, 8) == 0);
    // 空配列
    assert(parseAnchorsJson("{\"anchors\":[]}", out, 8) == 0);
}

int main() {
    test_slot_index();
    test_in_slot_windows();
    test_slot_exclusive();
    test_ms_until_slot();
    test_superframe_index();
    test_build_ranges_json();
    test_parse_anchors_json();
    printf("all native tests passed\n");
    return 0;
}
