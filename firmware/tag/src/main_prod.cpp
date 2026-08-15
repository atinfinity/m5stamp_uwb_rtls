// タグ FW 本番モード (Step 2/3: アンカー巡回 + TDMA + Wi-Fi/MQTT)
//
// 動作 (rtls-design.md §4.4, §4.9 / Issue #6):
//   - Wi-Fi 接続 + SNTP 同期 (5 分毎・スムーズ補正 = スルー) で壁時計を持つ
//   - 自スロット (アドレスから決まる 90 ms 窓) が来たら担当アンカーへ順次 DS-TWR
//   - 距離セットを rtls/tag/{addr}/ranges へ publish
//   - rtls/tag/{addr}/anchors (retained) を subscribe し、担当アンカーリストを更新
//
// ビルド設定 (platformio.ini の build_flags):
//   WIFI_SSID / WIFI_PASS / MQTT_HOST / SNTP_SERVER / NODE_ADDR
#include <Arduino.h>
#include <M5Stamp_UWB.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <esp_sntp.h>
#include <sys/time.h>

#include <rtls_common.h>
#include <rtls_msg.h>
#include <rtls_slots.h>

#ifndef NODE_ADDR
#define NODE_ADDR 0x0001
#endif
#ifndef WIFI_SSID
#define WIFI_SSID "rtls-ap"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "rtls-pass"
#endif
#ifndef MQTT_HOST
#define MQTT_HOST "192.168.1.10"
#endif
#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif
#ifndef SNTP_SERVER
#define SNTP_SERVER MQTT_HOST  // 既定: 測位サーバーホストの chrony (§4.9)
#endif

static constexpr size_t kMaxAnchors  = 6;   // 担当リスト上限 (先頭 4 台に測距)
static constexpr size_t kRangePerCycle = 4;
static constexpr uint32_t kSntpIntervalMs = 5 * 60 * 1000;  // §4.9: 5 分毎

static M5Stamp_UWB uwb;
static WiFiClient wifiClient;
static PubSubClient mqtt(wifiClient);

static uint16_t anchorList[kMaxAnchors] = {0x0010, 0x0011, 0x0013, 0x0014};  // 初期値: セル A
static size_t anchorCount = 4;
static uint32_t seq = 0;
static uint64_t lastSuperframe = 0;
static char topicRanges[40];
static char topicAnchors[40];
static char payload[512];

static uint64_t epochMs() {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    return static_cast<uint64_t>(tv.tv_sec) * 1000ULL + tv.tv_usec / 1000ULL;
}

static bool timeSynced() {
    return sntp_get_sync_status() != SNTP_SYNC_STATUS_RESET || epochMs() > 1600000000000ULL;
}

static void onMqttMessage(char* topic, byte* data, unsigned int len) {
    if (strcmp(topic, topicAnchors) != 0 || len >= sizeof(payload)) {
        return;
    }
    memcpy(payload, data, len);
    payload[len] = '\0';
    uint16_t parsed[kMaxAnchors];
    size_t n = rtls::parseAnchorsJson(payload, parsed, kMaxAnchors);
    if (n >= 3) {  // 3 台未満のリストでは測位できないため無視
        memcpy(anchorList, parsed, n * sizeof(uint16_t));
        anchorCount = n;
        Serial.printf("# anchors updated: %u entries\n", (unsigned)n);
    }
}

static void connectWifi() {
    if (WiFi.status() == WL_CONNECTED) return;
    Serial.printf("# wifi connecting to %s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
        delay(250);
    }
    Serial.printf("# wifi %s\n", WiFi.status() == WL_CONNECTED ? "connected" : "FAILED");
}

static void connectMqtt() {
    if (mqtt.connected()) return;
    char clientId[24];
    snprintf(clientId, sizeof(clientId), "rtls-tag-%04X", (unsigned)NODE_ADDR);
    if (mqtt.connect(clientId)) {
        mqtt.subscribe(topicAnchors, 1);
        Serial.println("# mqtt connected");
    }
}

static void initUwbOrHalt() {
    while (!uwb.begin(rtls::makeUwbConfig())) {
        Serial.printf("# uwb begin failed: %s — retrying\n", uwb.lastErrorName());
        uwb.hardReset();
        delay(1000);
    }
    Serial.printf("# tag(prod) addr=0x%04X chip=%s\n", (unsigned)NODE_ADDR, uwb.chipName());
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    snprintf(topicRanges, sizeof(topicRanges), "rtls/tag/0x%04X/ranges", (unsigned)NODE_ADDR);
    snprintf(topicAnchors, sizeof(topicAnchors), "rtls/tag/0x%04X/anchors", (unsigned)NODE_ADDR);

    initUwbOrHalt();
    connectWifi();

    // SNTP: スムーズ補正 (時刻ジャンプでスロット判定が飛ぶのを防ぐ, §4.9)
    sntp_set_sync_mode(SNTP_SYNC_MODE_SMOOTH);
    sntp_set_sync_interval(kSntpIntervalMs);
    configTime(0, 0, SNTP_SERVER);

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(onMqttMessage);
    mqtt.setBufferSize(512);
    connectMqtt();
}

static void runRangingCycle(uint64_t cycle_t_ms) {
    rtls::RangeEntry entries[kRangePerCycle];
    size_t n = anchorCount < kRangePerCycle ? anchorCount : kRangePerCycle;
    for (size_t i = 0; i < n; i++) {
        M5Stamp_UWBDSRangeConfig cfg = rtls::makeDsRangeConfig(NODE_ADDR, anchorList[i]);
        M5Stamp_UWBDSRangeResult res = uwb.requestDSRange(cfg);
        if (!res.success) {
            delay(1 + (esp_random() % 5));  // 乱数バックオフ後 1 回だけリトライ (§4.4)
            res = uwb.requestDSRange(cfg);
        }
        entries[i] = {anchorList[i], res.success ? res.distanceMm : 0, res.success};
    }
    seq++;
    size_t len = rtls::buildRangesJson(payload, sizeof(payload), NODE_ADDR, seq,
                                       cycle_t_ms, entries, n);
    if (len > 0 && mqtt.connected()) {
        mqtt.publish(topicRanges, payload);
    }
}

void loop() {
    connectWifi();
    connectMqtt();
    mqtt.loop();

    if (!timeSynced()) {
        delay(100);  // SNTP 同期前はスロット判定できない
        return;
    }

    const uint64_t now = epochMs();
    const int slot = rtls::slotIndexForTag(NODE_ADDR, rtls::kTagAddrBase);
    const uint64_t frame = rtls::superframeIndex(now);

    if (rtls::inSlot(now, slot) && frame != lastSuperframe) {
        lastSuperframe = frame;  // 1 スーパーフレーム 1 回
        runRangingCycle(now);
        return;
    }

    // 次スロットまで待機 (MQTT 処理のため最大 20 ms 刻み)
    uint32_t wait = rtls::msUntilSlot(now, slot);
    delay(wait > 20 ? 20 : (wait > 0 ? wait : 1));
}
