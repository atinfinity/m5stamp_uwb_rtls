// rtls_slots.h — TDMA スーパーフレーム/スロット判定 (rtls-design.md §4.4)
// Arduino 非依存 (ホストでネイティブテスト可能)。
#pragma once

#include <cstdint>

namespace rtls {

// スーパーフレーム 500 ms / スロット周期 100 ms (有効 90 ms + ガード 10 ms)。
// タグ 5 台 × 2 Hz。Step 1 の実測値でここを確定させる (ds-twr-design.md §3.3)。
constexpr uint32_t kSuperframeMs = 500;
constexpr uint32_t kSlotPeriodMs = 100;
constexpr uint32_t kSlotGuardMs  = 10;
constexpr uint32_t kSlotActiveMs = kSlotPeriodMs - kSlotGuardMs;  // 90 ms

// タグアドレス (0x0001..) → スロット番号 (0..)
constexpr int slotIndexForTag(uint16_t tag_addr, uint16_t tag_addr_base) {
    return static_cast<int>(tag_addr - tag_addr_base);
}

// epoch_ms (SNTP 同期済みの実時刻) が自スロットの有効窓内か
constexpr bool inSlot(uint64_t epoch_ms, int slot_idx) {
    const uint32_t pos = static_cast<uint32_t>(epoch_ms % kSuperframeMs);
    const uint32_t start = static_cast<uint32_t>(slot_idx) * kSlotPeriodMs;
    return pos >= start && pos < start + kSlotActiveMs;
}

// 現在のスーパーフレーム番号 (1 スロット 1 回実行の重複防止に使う)
constexpr uint64_t superframeIndex(uint64_t epoch_ms) {
    return epoch_ms / kSuperframeMs;
}

// 次に自スロットが始まるまでの待ち時間 [ms] (0 = 今スロット内)
constexpr uint32_t msUntilSlot(uint64_t epoch_ms, int slot_idx) {
    const uint32_t pos = static_cast<uint32_t>(epoch_ms % kSuperframeMs);
    const uint32_t start = static_cast<uint32_t>(slot_idx) * kSlotPeriodMs;
    if (pos >= start && pos < start + kSlotActiveMs) {
        return 0;
    }
    if (pos < start) {
        return start - pos;
    }
    return kSuperframeMs - pos + start;
}

}  // namespace rtls
