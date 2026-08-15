// TDoA PoC: ブリンク送信ノード (tdoa-design.md §6 PoC-1/2)
// BLINK_INTERVAL_MS 毎にブロードキャストフレームを 1 発送信するだけの最小ノード。
// マスターアンカー (既知位置からの同期ブリンク) とタグ (測位対象ブリンク) の
// どちらの模擬にも使う (NODE_ADDR を変えて書き込む)。
//
// ペイロード (5 byte): 'B' + uint32 seq (LE)。listener 側がこの seq で突き合わせる。
#include <Arduino.h>
#include <M5Stamp_UWB.h>
#include <rtls_common.h>

#ifndef NODE_ADDR
#define NODE_ADDR 0x00F0
#endif
#ifndef BLINK_INTERVAL_MS
#define BLINK_INTERVAL_MS 100
#endif

static M5Stamp_UWB uwb;
static uint32_t seq      = 0;
static uint32_t lastSend = 0;
static uint32_t okCount  = 0;
static uint32_t errCount = 0;

void setup() {
    Serial.begin(115200);
    delay(1000);
    while (!uwb.begin(rtls::makeUwbConfig())) {
        Serial.printf("# uwb begin failed: %s — retrying\n", uwb.lastErrorName());
        uwb.hardReset();
        delay(1000);
    }
    Serial.printf("# tdoa_blink addr=0x%04X interval_ms=%d chip=%s\n", (unsigned)NODE_ADDR,
                  (int)BLINK_INTERVAL_MS, uwb.chipName());
}

void loop() {
    uint32_t now = millis();
    if (now - lastSend < BLINK_INTERVAL_MS) {
        delay(1);
        return;
    }
    lastSend = now;

    uint8_t payload[5];
    payload[0] = 'B';
    payload[1] = (uint8_t)(seq & 0xFF);
    payload[2] = (uint8_t)((seq >> 8) & 0xFF);
    payload[3] = (uint8_t)((seq >> 16) & 0xFF);
    payload[4] = (uint8_t)((seq >> 24) & 0xFF);

    M5Stamp_UWBFrameConfig frame;
    frame.panId = rtls::kPanId;
    frame.src   = NODE_ADDR;
    frame.dst   = 0xFFFF;  // ブロードキャスト

    M5Stamp_UWBTxResult res = uwb.sendFrame(payload, sizeof(payload), frame);
    if (res.success) {
        okCount++;
    } else {
        errCount++;
    }
    seq++;

    if (seq % 100 == 0) {
        Serial.printf("# sent=%lu ok=%lu err=%lu\n", (unsigned long)seq,
                      (unsigned long)okCount, (unsigned long)errCount);
    }
}
