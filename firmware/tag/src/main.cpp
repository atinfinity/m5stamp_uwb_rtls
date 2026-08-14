// タグ FW (Step 1: DS-TWR 1対1計測モード)
// TARGET_ANCHOR へ RANGE_INTERVAL_MS 間隔で DS-TWR を行い、
// 1 行 1 測距の CSV をシリアルへ出力する。tools/step1/capture.py で採取する。
//
// CSV 列: seq,ok,d_mm,elapsed_ms,exchange_us,err
//   seq         このFWが振る通し番号(ライブラリの sequence とは別)
//   ok          1=成功 0=失敗
//   d_mm        測距距離 [mm](失敗時 0)
//   elapsed_ms  ライブラリ報告の所要時間 [ms]
//   exchange_us requestDSRange() 呼出し全体の実測時間 [µs](ホスト処理込み)
//   err         失敗時のエラー名(成功時 "-")
//
// ds-twr-design.md §6-1/§6-2(静的精度・タイミング実測)に対応。
#include <Arduino.h>
#include <M5Stamp_UWB.h>
#include <rtls_common.h>

#ifndef NODE_ADDR
#define NODE_ADDR 0x0001
#endif
#ifndef TARGET_ANCHOR
#define TARGET_ANCHOR 0x0010
#endif
#ifndef RANGE_INTERVAL_MS
#define RANGE_INTERVAL_MS 50
#endif

static M5Stamp_UWB uwb;

static uint32_t seq        = 0;
static uint32_t okCount    = 0;
static uint32_t errCount   = 0;
static uint32_t lastRange  = 0;
static uint32_t lastReport = 0;

static void initUwbOrHalt() {
    while (!uwb.begin(rtls::makeUwbConfig())) {
        Serial.printf("# uwb begin failed: %s — retrying\n", uwb.lastErrorName());
        uwb.hardReset();
        delay(1000);
    }
    Serial.printf("# tag addr=0x%04X anchor=0x%04X interval_ms=%d chip=%s\n",
                  (unsigned)NODE_ADDR, (unsigned)TARGET_ANCHOR, (int)RANGE_INTERVAL_MS,
                  uwb.chipName());
    Serial.println("seq,ok,d_mm,elapsed_ms,exchange_us,err");
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    initUwbOrHalt();
}

void loop() {
    uint32_t now = millis();
    if (now - lastRange < RANGE_INTERVAL_MS) {
        return;
    }
    lastRange = now;

    M5Stamp_UWBDSRangeConfig range = rtls::makeDsRangeConfig(NODE_ADDR, TARGET_ANCHOR);
    uint32_t t0                    = micros();
    M5Stamp_UWBDSRangeResult res   = uwb.requestDSRange(range);
    uint32_t exchangeUs            = micros() - t0;

    seq++;
    if (res.success) {
        okCount++;
        Serial.printf("%lu,1,%ld,%lu,%lu,-\n", (unsigned long)seq, (long)res.distanceMm,
                      (unsigned long)res.elapsedMs, (unsigned long)exchangeUs);
    } else {
        errCount++;
        Serial.printf("%lu,0,0,%lu,%lu,%s\n", (unsigned long)seq,
                      (unsigned long)res.elapsedMs, (unsigned long)exchangeUs,
                      uwb.lastErrorName());
    }

    // 10 秒ごとにサマリ(capture.py は '#' 行をメタデータとして扱う)
    if (now - lastReport >= 10000) {
        float rate = seq ? (100.0f * okCount / seq) : 0.0f;
        Serial.printf("# summary seq=%lu ok=%lu err=%lu success=%.1f%%\n",
                      (unsigned long)seq, (unsigned long)okCount, (unsigned long)errCount,
                      rate);
        lastReport = now;
    }
}
