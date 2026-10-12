// SS-TWR のクロックオフセット補償 (CFO 補正, ss-twr-design.md §2.2)。
// 公式ライブラリの requestRange() は補償を行わない (Issue #14 で実機確認) ため、
// タグ側で Response 受信直後の dwt_readclockoffset() を使って距離を補正する。
// SDK に依存しない純粋関数にしてあり、ネイティブテストで検証する。
#pragma once

#include <cstdint>

namespace rtls {

constexpr double kSpeedOfLightMps = 299702547.0;   // ライブラリと同じ値 (空気中)
constexpr double kUusToSeconds    = 512.0 / 499.2e6;  // 1 UWB µs = 1.0256 µs
constexpr double kClockOffsetUnit = 1.0 / (1 << 26);  // dwt_readclockoffset() の 1 LSB

// SS-TWR の生距離 rawMm を補正した距離 [mm] を返す。
//   clockOffset        Response 受信時の dwt_readclockoffset() (int16, 2^-26 単位)
//   responseTxDelayUus アンカーの応答遅延 T_reply (rtls::kSsResponseTxDelayUus)
// Qorvo SS-TWR サンプルの ToF = (T_round − T_reply × (1 − ratio)) / 2 と同じ補正を、
// 距離の差分 c × T_reply × ratio / 2 として加える。T_reply には実測値ではなく設定値を使う
// (アンテナ遅延と遅延送信の切り捨てによる差は数 ns で、補正量への影響は 1e-6 倍以下)。
inline int32_t ssCfoCorrectedMm(int32_t rawMm, int16_t clockOffset, uint32_t responseTxDelayUus) {
    const double ratio  = clockOffset * kClockOffsetUnit;
    const double tReply = responseTxDelayUus * kUusToSeconds;
    const double corrMm = kSpeedOfLightMps * tReply * ratio / 2.0 * 1000.0;
    const double mm     = rawMm + corrMm;
    return static_cast<int32_t>(mm >= 0 ? mm + 0.5 : mm - 0.5);
}

}  // namespace rtls
