// タグ FW (Step 1: 計測モード, DS-TWR / SS-TWR 両対応)
// TARGET_ANCHORS のアンカーへ RANGE_INTERVAL_MS 間隔で巡回測距を行い、
// 1 行 1 測距の CSV をシリアルへ出力する。tools/step1/capture.py で採取する。
//
// 方式は build env で切替 (platformio.ini):
//   env:tag_step1     … DS-TWR (既定)
//   env:tag_step1_ss  … SS-TWR (-DUSE_SS_TWR)。CSV 形式は共通で、
//                       ヘッダ行の mode= により解析側 (analyze.py) が区別する。
// SS-TWR の検証観点 (CFO 補償の有無 = 静的誤差) は ss-twr-design.md §2.2/§6。
//
// 対象アンカー:
//   -DTARGET_ANCHOR=0x0010                  … 1 対 1 (従来どおり)
//   -DTARGET_ANCHORS=0x0010,0x0011,0x0012   … 複数アンカー巡回 (Issue #43)。
//                                              1 サイクルで全アンカーを順に測距する
//   -DINTER_ANCHOR_GAP_MS=2                 … アンカー切替ギャップ [ms]
//                                              (既定 rtls::kDsInterAnchorGapMs)
//
// CSV 列: seq,anchor,ok,d_mm,elapsed_ms,exchange_us,cycle_us,err
//   seq         サイクル通し番号 (同一サイクルの全アンカー行で共通)
//   anchor      相手アンカーのショートアドレス (0x0010 形式)
//   ok          1=成功 0=失敗
//   d_mm        測距距離 [mm](失敗時 0)
//   elapsed_ms  ライブラリ報告の所要時間 [ms]
//   exchange_us requestDSRange() 呼出し全体の実測時間 [µs](ホスト処理込み)
//   cycle_us    サイクル全体 (全アンカー + ギャップ) の所要時間 [µs]。
//               サイクル最後のアンカー行にのみ入り、それ以外は 0
//   err         失敗時のエラー名(成功時 "-")
//
// ds-twr-design.md §6 の 1./2./5.(静的精度・タイミング実測・アンカー間ギャップ)に対応。
#include <Arduino.h>
#include <M5Stamp_UWB.h>
#include <rtls_common.h>

#ifndef NODE_ADDR
#define NODE_ADDR 0x0001
#endif
#ifndef TARGET_ANCHOR
#define TARGET_ANCHOR 0x0010
#endif
#ifndef TARGET_ANCHORS
#define TARGET_ANCHORS TARGET_ANCHOR
#endif
#ifndef RANGE_INTERVAL_MS
#define RANGE_INTERVAL_MS 50
#endif
#ifndef INTER_ANCHOR_GAP_MS
#define INTER_ANCHOR_GAP_MS rtls::kDsInterAnchorGapMs
#endif

static M5Stamp_UWB uwb;

#ifdef USE_SS_TWR
#define RANGING_MODE "SS"
#else
#define RANGING_MODE "DS"
#endif

static const uint16_t kAnchors[]   = {TARGET_ANCHORS};
static const size_t kAnchorCount   = sizeof(kAnchors) / sizeof(kAnchors[0]);
static const uint32_t kGapMs       = INTER_ANCHOR_GAP_MS;

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
    Serial.printf("# tag addr=0x%04X anchors=", (unsigned)NODE_ADDR);
    for (size_t i = 0; i < kAnchorCount; i++) {
        Serial.printf("%s0x%04X", i ? "," : "", (unsigned)kAnchors[i]);
    }
    Serial.printf(" gap_ms=%lu interval_ms=%d mode=%s chip=%s\n", (unsigned long)kGapMs,
                  (int)RANGE_INTERVAL_MS, RANGING_MODE, uwb.chipName());
    Serial.println("seq,anchor,ok,d_mm,elapsed_ms,exchange_us,cycle_us,err");
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
    seq++;

    const uint32_t cycleT0 = micros();
    for (size_t i = 0; i < kAnchorCount; i++) {
        const uint16_t anchor = kAnchors[i];
        const uint32_t t0     = micros();
#ifdef USE_SS_TWR
        M5Stamp_UWBRangeResult res = uwb.requestRange(rtls::makeSsRangeConfig(NODE_ADDR, anchor));
#else
        M5Stamp_UWBDSRangeResult res = uwb.requestDSRange(rtls::makeDsRangeConfig(NODE_ADDR, anchor));
#endif
        const uint32_t exchangeUs = micros() - t0;
        const bool last           = (i + 1 == kAnchorCount);
        const uint32_t cycleUs    = last ? (micros() - cycleT0) : 0;

        if (res.success) {
            okCount++;
            Serial.printf("%lu,0x%04X,1,%ld,%lu,%lu,%lu,-\n", (unsigned long)seq, (unsigned)anchor,
                          (long)res.distanceMm, (unsigned long)res.elapsedMs,
                          (unsigned long)exchangeUs, (unsigned long)cycleUs);
        } else {
            errCount++;
            Serial.printf("%lu,0x%04X,0,0,%lu,%lu,%lu,%s\n", (unsigned long)seq, (unsigned)anchor,
                          (unsigned long)res.elapsedMs, (unsigned long)exchangeUs,
                          (unsigned long)cycleUs, uwb.lastErrorName());
        }
        if (!last && kGapMs > 0) {
            delay(kGapMs);  // 前アンカーが TX→RX に戻る猶予 (ds-twr-design.md §3.3)
        }
    }

    // 10 秒ごとにサマリ(capture.py は '#' 行をメタデータとして扱う)
    if (now - lastReport >= 10000) {
        const uint32_t trials = seq * kAnchorCount;
        float rate = trials ? (100.0f * okCount / trials) : 0.0f;
        Serial.printf("# summary cycles=%lu ok=%lu err=%lu success=%.1f%%\n",
                      (unsigned long)seq, (unsigned long)okCount, (unsigned long)errCount,
                      rate);
        lastReport = now;
    }
}
