// rtls_common.h — 全ノード共有の定数(ピン・アドレス・タイミング)
// 基本設計 rtls-design.md §4.2 / ds-twr-design.md §3 に対応。
// タイミング初期値は M5Stack 公式サンプル(MIT)の DS_TWR_TAG/ANCHOR・SS_TWR_TAG/ANCHOR 準拠
// (https://github.com/m5stack/M5Stamp-UWB/tree/main/examples)。Step 1 の実測後にここで確定させる。
#pragma once

#include <cstdint>

#include <M5Stamp_UWB.h>

// ---- Stamp C5 <-> Stamp UWB F (FPC 直結) ピン割当 ----
namespace rtls {

constexpr int8_t kPinCs     = 11;
constexpr int8_t kPinRst    = 25;
constexpr int8_t kPinIrq    = 0;
constexpr int8_t kPinWakeup = 24;
constexpr int8_t kPinGp7    = 23;
constexpr int8_t kPinSck    = 12;
constexpr int8_t kPinMiso   = 26;
constexpr int8_t kPinMosi   = 27;

// ---- アドレス体系 (rtls-design.md §4.2) ----
constexpr uint16_t kPanId           = 0xDECA;
constexpr uint16_t kAnchorAddrBase  = 0x0010;  // 0x0010〜0x001B (最大12台)
constexpr uint16_t kTagAddrBase     = 0x0001;  // 0x0001〜0x0005

// ---- DS-TWR タイミング (ds-twr-design.md §3.3, Step 1 実測で確定) ----
constexpr uint32_t kDsResponseRxAfterTxDelayUus      = 1500;
constexpr uint32_t kDsResponseTxDelayUus             = 3000;
constexpr uint32_t kDsFinalTxDelayUus                = 1800;
constexpr uint32_t kDsFinalRxAfterResponseTxDelayUus = 500;
constexpr uint32_t kDsResultRxAfterFinalTxDelayUus   = 500;
constexpr uint32_t kDsRxTimeoutUus                   = 3000;
constexpr uint32_t kDsHostTimeoutMs                  = 100;
constexpr uint8_t  kDsResultRepeatCount              = 3;
constexpr uint32_t kDsResultRepeatGapMs              = 3;

inline M5Stamp_UWBConfig makeUwbConfig() {
    M5Stamp_UWBConfig config;
    config.pin_cs     = kPinCs;
    config.pin_rst    = kPinRst;
    config.pin_irq    = kPinIrq;
    config.pin_wakeup = kPinWakeup;
    config.pin_gp7    = kPinGp7;
    config.pin_sck    = kPinSck;
    config.pin_miso   = kPinMiso;
    config.pin_mosi   = kPinMosi;
    return config;
}

// ---- SS-TWR タイミング (ss-twr-design.md §3, 公式サンプル準拠) ----
constexpr uint32_t kSsResponseRxAfterTxDelayUus = 500;
constexpr uint32_t kSsResponseTxDelayUus        = 3000;
constexpr uint32_t kSsRxTimeoutUus              = 4500;
constexpr uint32_t kSsHostTimeoutMs             = 100;

inline M5Stamp_UWBRangeConfig makeSsRangeConfig(uint16_t initiator, uint16_t responder) {
    M5Stamp_UWBRangeConfig range;
    range.panId                     = kPanId;
    range.initiatorAddress          = initiator;
    range.responderAddress          = responder;
    range.responseRxAfterTxDelayUus = kSsResponseRxAfterTxDelayUus;
    range.responseTxDelayUus        = kSsResponseTxDelayUus;
    range.rxTimeoutUus              = kSsRxTimeoutUus;
    range.hostTimeoutMs             = kSsHostTimeoutMs;
    return range;
}

inline M5Stamp_UWBDSRangeConfig makeDsRangeConfig(uint16_t initiator, uint16_t responder) {
    M5Stamp_UWBDSRangeConfig range;
    range.panId                          = kPanId;
    range.initiatorAddress               = initiator;
    range.responderAddress               = responder;
    range.responseRxAfterTxDelayUus      = kDsResponseRxAfterTxDelayUus;
    range.responseTxDelayUus             = kDsResponseTxDelayUus;
    range.finalTxDelayUus                = kDsFinalTxDelayUus;
    range.finalRxAfterResponseTxDelayUus = kDsFinalRxAfterResponseTxDelayUus;
    range.resultRxAfterFinalTxDelayUus   = kDsResultRxAfterFinalTxDelayUus;
    range.rxTimeoutUus                   = kDsRxTimeoutUus;
    range.hostTimeoutMs                  = kDsHostTimeoutMs;
    range.resultRepeatCount              = kDsResultRepeatCount;
    range.resultRepeatGapMs              = kDsResultRepeatGapMs;
    return range;
}

}  // namespace rtls
