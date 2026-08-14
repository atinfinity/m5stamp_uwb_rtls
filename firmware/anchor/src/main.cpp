// アンカー FW (Step 1: DS-TWR 応答専用)
// 自局アドレス(NODE_ADDR)宛の DS-TWR 要求に応答し続ける。
// rtls-design.md §4.3 / ds-twr-design.md §3 参照。
#include <Arduino.h>
#include <M5Stamp_UWB.h>
#include <rtls_common.h>

#ifndef NODE_ADDR
#define NODE_ADDR 0x0010
#endif

static M5Stamp_UWB uwb;

static uint32_t okCount    = 0;
static uint32_t errCount   = 0;
static uint32_t lastReport = 0;

static void initUwbOrHalt() {
    while (!uwb.begin(rtls::makeUwbConfig())) {
        Serial.printf("# uwb begin failed: %s — retrying\n", uwb.lastErrorName());
        uwb.hardReset();
        delay(1000);
    }
    Serial.printf("# anchor addr=0x%04X chip=%s id=0x%08lX\n", (unsigned)NODE_ADDR,
                  uwb.chipName(), (unsigned long)uwb.deviceId());
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    initUwbOrHalt();
}

void loop() {
    // initiatorAddress はワイルドカード的に扱えないため、応答側は自局を
    // responder に設定して待ち受ける。相手 (initiator) は結果から知る。
    M5Stamp_UWBDSRangeConfig range = rtls::makeDsRangeConfig(rtls::kTagAddrBase, NODE_ADDR);
    M5Stamp_UWBDSResponderResult res = uwb.respondDSRange(range);
    if (res.success) {
        okCount++;
    } else if (res.error != M5Stamp_UWBError::RxTimeout) {
        // 待機中のタイムアウトは正常。それ以外のみ数える。
        errCount++;
    }

    // 10 秒ごとに統計を出力(シリアル負荷を抑える)
    uint32_t now = millis();
    if (now - lastReport >= 10000) {
        Serial.printf("# ok=%lu err=%lu heap=%lu\n", (unsigned long)okCount,
                      (unsigned long)errCount, (unsigned long)ESP.getFreeHeap());
        lastReport = now;
    }
}
