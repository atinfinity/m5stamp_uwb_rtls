// タグ FW 本番モード (Step 2/3 + B案タグ上計算, Issue #6/#28)
//
// 動作 (rtls-design.md §4.4, §4.9 / tag-design.md §2〜§7):
//   - Wi-Fi + SNTP (5 分毎スムーズ補正) で実時刻を持ち、TDMA スロットで測距
//   - rtls/config/anchors・rtls/config/tuning (retained, version 付き) を受信して
//     NVS へ永続化し、rtls_solver によるタグ上解算とオンボードセル選択を行う
//   - 動作モード (NVS 永続、シリアルコマンド "mode <M>" で切替):
//       HYBRID     … ranges + position を MQTT へ (既定。A案サーバーと併用可)
//       QUIET      … position のみ MQTT へ
//       STANDALONE … UART バイナリフレームのみ (tag-design.md §7)
//   - 設定未受信のうちは解算せず ranges 送信のみ (A案互換で動作)
//   - SNTP 未同期時は kSuperframeMs 周期のフリーラン (単一タグ前提のフォールバック)
//
// ビルド設定 (platformio.ini): WIFI_SSID / WIFI_PASS / MQTT_HOST / SNTP_SERVER /
//   NODE_ADDR / RTLS_UART_TX / RTLS_UART_RX
#include <Arduino.h>
#include <M5Stamp_UWB.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <esp_sntp.h>
#include <sys/time.h>

#include <rtls_common.h>
#include <rtls_config_msg.h>
#include <rtls_msg.h>
#include <rtls_slots.h>

#include <pipeline.hpp>  // rtls_solver

#include "config_store.h"

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
#ifndef RTLS_UART_TX
#define RTLS_UART_TX -1  // -1 = Serial1 の既定ピン
#endif
#ifndef RTLS_UART_RX
#define RTLS_UART_RX -1
#endif

static constexpr size_t kRangePerCycle   = 4;
static constexpr uint32_t kSntpIntervalMs = 5 * 60 * 1000;  // §4.9: 5 分毎

static M5Stamp_UWB uwb;
static WiFiClient wifiClient;
static PubSubClient mqtt(wifiClient);

// ---- 設定・解算状態 ----
static rtls::AnchorsConfig gCfg;      // rtls/config/anchors (パース済み)
static bool gCfgValid       = false;
static uint32_t gCfgVersion = 0;
static rtls::TuningDef gTuning;
static uint32_t gTuningVersion = 0;
static rtls_solver::TagPipeline* gPipeline = nullptr;
static int gCell = -1;                // オンボードセル (index, -1=未確定)
static cfgstore::Mode gMode = cfgstore::Mode::HYBRID;

// 設定未受信時の測距先 (A案互換: サーバーの anchors 配信 or 既定セル A)
static uint16_t fallbackList[rtls::kMaxCellAnchors] = {0x0010, 0x0011, 0x0013, 0x0014};
static size_t fallbackCount = 4;

static uint32_t seq        = 0;
static uint64_t lastSuperframe = 0;
static uint32_t lastFreerun    = 0;
static char topicRanges[40];
static char topicAnchors[40];
// 12 アンカー + 8 セルの anchors config (~2 KB) を受けられるサイズ (tag-design §5)
static char payload[2048];
static char serialLine[48];
static size_t serialLen = 0;

static uint64_t epochMs() {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    return (uint64_t)tv.tv_sec * 1000ULL + tv.tv_usec / 1000ULL;
}

static bool timeSynced() {
    return sntp_get_sync_status() != SNTP_SYNC_STATUS_RESET || epochMs() > 1600000000000ULL;
}

// ---- 設定の適用 (NVS 復元と MQTT 受信の共通経路) ----

static rtls_solver::Tuning toSolverTuning(const rtls::TuningDef& t) {
    rtls_solver::Tuning s;
    s.max_age_ms        = t.max_age_ms;
    s.v_max_ms          = t.v_max_ms;
    s.gate_margin_m     = t.gate_margin_m;
    s.residual_gate_m   = t.residual_gate_m;
    s.sigma_a           = t.sigma_a;
    s.sigma_m_floor     = t.sigma_m_floor;
    s.stale_sec         = t.stale_sec;
    s.lost_sec          = t.lost_sec;
    return s;
}

static void rebuildPipeline() {
    delete gPipeline;
    gPipeline = nullptr;
    if (!gCfgValid) return;
    rtls_solver::AnchorInfo table[rtls::kMaxCfgAnchors];
    for (int i = 0; i < gCfg.n_anchors; i++) {
        table[i] = {gCfg.anchors[i].addr, gCfg.anchors[i].x, gCfg.anchors[i].y,
                    gCfg.anchors[i].z, gCfg.anchors[i].bias_mm};
    }
    gPipeline = new rtls_solver::TagPipeline(table, gCfg.n_anchors, gCfg.tag_height_m,
                                             toSolverTuning(gTuning));
    gCell = -1;  // セルは次の解算で再判定
    Serial.printf("# solver ready: anchors=%d cells=%d cfg_v=%lu tune_v=%lu\n",
                  gCfg.n_anchors, gCfg.n_cells, (unsigned long)gCfgVersion,
                  (unsigned long)gTuningVersion);
}

static bool applyAnchorsJson(const char* json, bool persist) {
    static char buf[2048];
    strncpy(buf, json, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    rtls::stripJsonSpaces(buf);
    rtls::AnchorsConfig parsed;
    if (!rtls::parseAnchorsConfig(buf, &parsed)) {
        Serial.println("# anchors config parse failed — keeping previous");
        return false;
    }
    if (parsed.version <= gCfgVersion) {
        return false;  // 古い/同一バージョンは無視
    }
    gCfg = parsed;
    gCfgValid = true;
    gCfgVersion = parsed.version;
    if (persist) cfgstore::saveAnchors(json, parsed.version);
    rebuildPipeline();
    return true;
}

static bool applyTuningJson(const char* json, bool persist) {
    static char buf[384];
    strncpy(buf, json, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    rtls::stripJsonSpaces(buf);
    rtls::TuningDef t;
    uint32_t ver = 0;
    if (!rtls::parseTuningConfig(buf, &t, &ver) || ver <= gTuningVersion) {
        return false;
    }
    gTuning = t;
    gTuningVersion = ver;
    if (persist) cfgstore::saveTuning(json, ver);
    rebuildPipeline();
    return true;
}

// ---- MQTT ----

static void onMqttMessage(char* topic, byte* data, unsigned int len) {
    if (len >= sizeof(payload)) return;
    memcpy(payload, data, len);
    payload[len] = '\0';
    if (strcmp(topic, "rtls/config/anchors") == 0) {
        applyAnchorsJson(payload, /*persist=*/true);
    } else if (strcmp(topic, "rtls/config/tuning") == 0) {
        applyTuningJson(payload, /*persist=*/true);
    } else if (strcmp(topic, topicAnchors) == 0 && !gCfgValid) {
        // A案互換: 設定未受信のうちはサーバーの担当アンカー配信に従う (§5)
        uint16_t parsed[rtls::kMaxCellAnchors];
        size_t n = rtls::parseAnchorsJson(payload, parsed, rtls::kMaxCellAnchors);
        if (n >= 3) {
            memcpy(fallbackList, parsed, n * sizeof(uint16_t));
            fallbackCount = n;
        }
    }
}

static void connectWifi() {
    // STANDALONE で AP 不在でも測距を止めないよう、再試行は 30 秒に 1 回・
    // ブロッキング待ちは初回接続時のみとする
    static uint32_t lastTry = 0;
    static bool firstTry = true;
    if (WiFi.status() == WL_CONNECTED) return;
    uint32_t now = millis();
    if (!firstTry && now - lastTry < 30000) return;
    lastTry = now;
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    if (firstTry) {
        for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
        firstTry = false;
        Serial.printf("# wifi %s\n",
                      WiFi.status() == WL_CONNECTED ? "connected" : "FAILED (retrying in bg)");
    }
}

static void connectMqtt() {
    if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
    char clientId[24];
    snprintf(clientId, sizeof(clientId), "rtls-tag-%04X", (unsigned)NODE_ADDR);
    if (mqtt.connect(clientId)) {
        mqtt.subscribe("rtls/config/anchors", 1);
        mqtt.subscribe("rtls/config/tuning", 1);
        mqtt.subscribe(topicAnchors, 1);
        Serial.println("# mqtt connected");
    }
}

// ---- シリアルコマンド ("mode HYBRID|STANDALONE|QUIET" / "status") ----

static void handleSerialCommand(const char* line) {
    if (strncasecmp(line, "mode ", 5) == 0) {
        cfgstore::Mode m;
        if (cfgstore::parseMode(line + 5, &m)) {
            gMode = m;
            cfgstore::setMode(m);
            Serial.printf("# mode = %s (saved)\n", cfgstore::modeName(m));
        } else {
            Serial.println("# usage: mode HYBRID|STANDALONE|QUIET");
        }
    } else if (strcasecmp(line, "status") == 0) {
        Serial.printf("# mode=%s cfg_v=%lu tune_v=%lu solver=%d cell=%d synced=%d\n",
                      cfgstore::modeName(gMode), (unsigned long)gCfgVersion,
                      (unsigned long)gTuningVersion, gPipeline != nullptr, gCell,
                      (int)timeSynced());
    }
}

static void pollSerial() {
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (serialLen > 0) {
                serialLine[serialLen] = '\0';
                handleSerialCommand(serialLine);
                serialLen = 0;
            }
        } else if (serialLen < sizeof(serialLine) - 1) {
            serialLine[serialLen++] = c;
        }
    }
}

// ---- 測距サイクル (tag-design.md §6) ----

static const uint16_t* cycleAnchors(size_t* count) {
    if (gCfgValid && gCell >= 0 && gCell < gCfg.n_cells) {
        *count = (size_t)gCfg.cells[gCell].n_anchors;
        if (*count > kRangePerCycle) *count = kRangePerCycle;
        return gCfg.cells[gCell].anchors;
    }
    if (gCfgValid && gCfg.n_cells > 0) {
        // セル未確定: 先頭セル (捕捉用) から開始
        *count = (size_t)gCfg.cells[0].n_anchors;
        if (*count > kRangePerCycle) *count = kRangePerCycle;
        return gCfg.cells[0].anchors;
    }
    *count = fallbackCount < kRangePerCycle ? fallbackCount : kRangePerCycle;
    return fallbackList;
}

static void runRangingCycle(uint64_t cycle_t_ms) {
    size_t n = 0;
    const uint16_t* list = cycleAnchors(&n);
    rtls::RangeEntry entries[kRangePerCycle];
    rtls_solver::RangeMeas meas[kRangePerCycle];
    for (size_t i = 0; i < n; i++) {
        M5Stamp_UWBDSRangeConfig cfg = rtls::makeDsRangeConfig(NODE_ADDR, list[i]);
        M5Stamp_UWBDSRangeResult res = uwb.requestDSRange(cfg);
        if (!res.success) {
            delay(1 + (esp_random() % 5));  // 乱数バックオフ後 1 回だけリトライ (§4.4)
            res = uwb.requestDSRange(cfg);
        }
        entries[i] = {list[i], res.success ? res.distanceMm : 0, res.success};
        meas[i]    = {list[i], res.success ? res.distanceMm : 0, res.success};
    }
    seq++;

    // ---- タグ上解算 (config 受信済みのときのみ) ----
    rtls_solver::PosOut pos;
    if (gPipeline != nullptr) {
        pos = gPipeline->process(seq, cycle_t_ms, cycle_t_ms, meas, (int)n);
        if (pos.valid && pos.state == rtls_solver::TrackState::TRACKING) {
            gCell = rtls::selectCell(gCfg.cells, gCfg.n_cells, pos.x, pos.y, gCell,
                                     gTuning.handover_margin_m);
        }
    }

    // ---- 出力 (モード別, tag-design.md §2) ----
    const bool sendRanges   = (gMode == cfgstore::Mode::HYBRID);
    const bool sendPosition = (gMode != cfgstore::Mode::STANDALONE);
    if (sendRanges && mqtt.connected()) {
        size_t len = rtls::buildRangesJson(payload, sizeof(payload), NODE_ADDR, seq,
                                           cycle_t_ms, entries, n);
        if (len > 0) mqtt.publish(topicRanges, payload);
    }
    if (pos.valid) {
        const char* state =
            pos.state == rtls_solver::TrackState::TRACKING   ? "TRACKING"
            : pos.state == rtls_solver::TrackState::COASTING ? "COASTING"
            : pos.state == rtls_solver::TrackState::STALE    ? "STALE"
                                                             : "LOST";
        const char* cell = (gCell >= 0) ? gCfg.cells[gCell].name : "";
        if (sendPosition && mqtt.connected()) {
            char posbuf[256];
            char topic[40];
            snprintf(topic, sizeof(topic), "rtls/tag/0x%04X/position", (unsigned)NODE_ADDR);
            if (rtls::buildPositionJson(posbuf, sizeof(posbuf), NODE_ADDR, pos.t_ms,
                                        pos.x, pos.y, pos.vx, pos.vy, pos.n_used,
                                        pos.rms, state, cell) > 0) {
                mqtt.publish(topic, posbuf);
            }
        }
        if (gMode == cfgstore::Mode::STANDALONE) {
            uint8_t frame[rtls::kUartFrameLen];
            uint8_t st = pos.state == rtls_solver::TrackState::TRACKING   ? 1
                         : pos.state == rtls_solver::TrackState::COASTING ? 2
                         : pos.state == rtls_solver::TrackState::STALE    ? 3
                                                                          : 0;
            rtls::buildUartFrame(frame, (uint8_t)(NODE_ADDR & 0xFF), st,
                                 (uint32_t)pos.t_ms, pos.x, pos.y, pos.vx, pos.vy,
                                 pos.rms, (uint8_t)pos.n_used);
            Serial1.write(frame, rtls::kUartFrameLen);
        }
    }
}

void setup() {
    Serial.begin(115200);
    Serial1.begin(115200, SERIAL_8N1, RTLS_UART_RX, RTLS_UART_TX);
    delay(1000);
    snprintf(topicRanges, sizeof(topicRanges), "rtls/tag/0x%04X/ranges", (unsigned)NODE_ADDR);
    snprintf(topicAnchors, sizeof(topicAnchors), "rtls/tag/0x%04X/anchors", (unsigned)NODE_ADDR);

    cfgstore::begin();
    gMode = cfgstore::mode();

    // NVS から設定を復元 (Wi-Fi 断・STANDALONE でも解算を継続できる)
    String json;
    uint32_t ver;
    if (cfgstore::loadTuning(&json, &ver)) {
        gTuningVersion = 0;  // 復元は無条件に適用
        applyTuningJson(json.c_str(), /*persist=*/false);
    }
    if (cfgstore::loadAnchors(&json, &ver)) {
        gCfgVersion = 0;
        applyAnchorsJson(json.c_str(), /*persist=*/false);
    }

    while (!uwb.begin(rtls::makeUwbConfig())) {
        Serial.printf("# uwb begin failed: %s — retrying\n", uwb.lastErrorName());
        uwb.hardReset();
        delay(1000);
    }
    Serial.printf("# tag(prod) addr=0x%04X mode=%s solver=%d chip=%s\n",
                  (unsigned)NODE_ADDR, cfgstore::modeName(gMode), gPipeline != nullptr,
                  uwb.chipName());

    connectWifi();
    sntp_set_sync_mode(SNTP_SYNC_MODE_SMOOTH);  // §4.9: スムーズ補正
    sntp_set_sync_interval(kSntpIntervalMs);
    configTime(0, 0, SNTP_SERVER);

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(onMqttMessage);
    mqtt.setBufferSize(2048);  // anchors config が載るサイズ
    connectMqtt();
}

void loop() {
    pollSerial();
    connectWifi();
    connectMqtt();
    mqtt.loop();

    if (timeSynced()) {
        const uint64_t now  = epochMs();
        const int slot      = rtls::slotIndexForTag(NODE_ADDR, rtls::kTagAddrBase);
        const uint64_t frame = rtls::superframeIndex(now);
        if (rtls::inSlot(now, slot) && frame != lastSuperframe) {
            lastSuperframe = frame;
            runRangingCycle(now);
            return;
        }
        uint32_t wait = rtls::msUntilSlot(now, slot);
        delay(wait > 20 ? 20 : (wait > 0 ? wait : 1));
    } else {
        // SNTP 未同期: 単一タグ前提のフリーラン (スロット規律なし, STANDALONE 向け)
        uint32_t now = millis();
        if (now - lastFreerun >= rtls::kSuperframeMs) {
            lastFreerun = now;
            runRangingCycle(now);
        } else {
            delay(10);
        }
    }
}
