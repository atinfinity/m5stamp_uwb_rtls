// TDoA PoC: リスナーノード (tdoa-design.md §6 PoC-1/2)
// ブリンクフレームを常時受信し、SDK 直叩きで取得した RX タイムスタンプを
// CSV でシリアルへ出力する。tools/tdoa/sync_analysis.py で解析する。
//
// ★PoC-1 の核心: 公式ライブラリの公開 API に RX タイムスタンプは無いため、
//   同梱 qm33120w_sdk の dwt_readrxtimestamp() を直接呼ぶ (40 bit,
//   1 tick = 1/(128*499.2 MHz) ≈ 15.65 ps, アンテナ遅延補正済み)。
//   実機での確認事項: receiveFrame() の実装が次の受信開始でタイムスタンプ
//   レジスタを上書きしないか (blink 毎に ticks が単調増加していれば OK)。
//
// CSV 列: src,seq,rx_ticks
//   src      送信元ショートアドレス (ブリンクノードの NODE_ADDR)
//   seq      ブリンクペイロード内の uint32 通し番号
//   rx_ticks 40bit RX タイムスタンプ (~17.2 s で周回。解析側でアンラップ)
#include <Arduino.h>
#include <M5Stamp_UWB.h>
#include <rtls_common.h>

extern "C" {
#include "qm33120w_sdk/deca_device_api.h"
}

#ifndef NODE_ADDR
#define NODE_ADDR 0x0020
#endif

static M5Stamp_UWB uwb;
static uint32_t rxCount   = 0;
static uint32_t badCount  = 0;
static uint32_t lastStats = 0;

void setup() {
    Serial.begin(115200);
    delay(1000);
    while (!uwb.begin(rtls::makeUwbConfig())) {
        Serial.printf("# uwb begin failed: %s — retrying\n", uwb.lastErrorName());
        uwb.hardReset();
        delay(1000);
    }
    Serial.printf("# tdoa_listener addr=0x%04X tick_ps=15650 chip=%s\n", (unsigned)NODE_ADDR,
                  uwb.chipName());
    Serial.println("src,seq,rx_ticks");
}

void loop() {
    uint8_t buf[32];
    M5Stamp_UWBRxResult res = uwb.receiveFrame(buf, sizeof(buf), 500);
    if (!res.success) {
        return;  // タイムアウトは正常 (ブリンク間隔より短い受信窓で回す)
    }
    if (res.payloadLength < 5 || buf[0] != 'B') {
        badCount++;
        return;  // ブリンク以外のフレーム (測距等) は無視
    }

    // ★受信直後にタイムスタンプを読む (次の receiveFrame 呼出し前)。
    //   第 2 引数はセグメント選択: QM33xxx/DW3XXX の dwt_uwb_driver では
    //   DWT_COMPAT_NONE を渡す (deca_device_api.h のコメントに明記)。
    uint8_t ts[5];
    dwt_readrxtimestamp(ts, DWT_COMPAT_NONE);
    uint64_t ticks = 0;
    for (int i = 4; i >= 0; i--) {
        ticks = (ticks << 8) | ts[i];  // 5 byte little-endian → uint64
    }

    uint32_t seq = (uint32_t)buf[1] | ((uint32_t)buf[2] << 8) | ((uint32_t)buf[3] << 16) |
                   ((uint32_t)buf[4] << 24);

    Serial.printf("0x%04X,%lu,%llu\n", (unsigned)res.src, (unsigned long)seq,
                  (unsigned long long)ticks);
    rxCount++;

    uint32_t now = millis();
    if (now - lastStats >= 10000) {
        Serial.printf("# rx=%lu ignored=%lu heap=%lu\n", (unsigned long)rxCount,
                      (unsigned long)badCount, (unsigned long)ESP.getFreeHeap());
        lastStats = now;
    }
}
