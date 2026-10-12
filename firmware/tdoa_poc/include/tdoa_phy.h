// TDoA PoC 用の PHY 設定 (tdoa-design.md §6.1)。
// 6.8 Mbps (ライブラリ既定) ではブリンクのデータ部の復号失敗 (RXFSL) が多く、正常受信率が
// 配置次第で 10〜72% に留まった。850 kbps では 84〜93.5% (Issue #16)。
// エアタイムは 16 byte フレームで約 183 µs → 約 340 µs に伸びる。
#pragma once

#include <M5Stamp_UWB.h>
#include <rtls_common.h>

namespace tdoa {

// listener と blink_tx は必ず同じ設定を使うこと (データレートが違うと復号できない)。
// channel 以外を変えるとライブラリは推奨プロファイルではなく全フィールドを指定値で使うため、
// データレート以外は M5Stamp_UWBPHYConfig の既定値 (Ch9 推奨値と同じ) のままにする。
inline M5Stamp_UWBPHYConfig makePhyConfig() {
    M5Stamp_UWBPHYConfig phy = rtls::makePhyConfig();
    phy.dataRate             = M5Stamp_UWBDataRate::Rate850K;
    // SFD タイムアウト = プリアンブル長 + 1 + SFD 長 - PAC = 128 + 1 + 8 - 8
    phy.sfdTimeout = 129;
    return phy;
}

}  // namespace tdoa
