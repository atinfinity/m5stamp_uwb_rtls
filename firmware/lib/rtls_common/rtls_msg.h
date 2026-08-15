// rtls_msg.h — MQTT ペイロードの生成/解析 (rtls-design.md §4.7)
// Arduino 非依存・外部ライブラリ非依存 (ホストでネイティブテスト可能)。
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace rtls {

struct RangeEntry {
    uint16_t anchor;
    int32_t d_mm;
    bool ok;
};

// ranges メッセージを buf に生成する。戻り値: 書き込んだ長さ (>= n なら失敗 = 0)。
// 形式: {"tag":"0x0001","seq":12,"t_ms":123,"ranges":[{"a":"0x0010","d_mm":5234,"ok":true},...]}
inline size_t buildRangesJson(char* buf, size_t n, uint16_t tag, uint32_t seq,
                              uint64_t t_ms, const RangeEntry* entries, size_t count) {
    size_t off = 0;
    int w = snprintf(buf + off, n - off,
                     "{\"tag\":\"0x%04X\",\"seq\":%lu,\"t_ms\":%llu,\"ranges\":[",
                     tag, static_cast<unsigned long>(seq),
                     static_cast<unsigned long long>(t_ms));
    if (w < 0 || static_cast<size_t>(w) >= n - off) return 0;
    off += static_cast<size_t>(w);
    for (size_t i = 0; i < count; i++) {
        w = snprintf(buf + off, n - off,
                     "%s{\"a\":\"0x%04X\",\"d_mm\":%ld,\"ok\":%s}",
                     i ? "," : "", entries[i].anchor,
                     static_cast<long>(entries[i].d_mm),
                     entries[i].ok ? "true" : "false");
        if (w < 0 || static_cast<size_t>(w) >= n - off) return 0;
        off += static_cast<size_t>(w);
    }
    w = snprintf(buf + off, n - off, "]}");
    if (w < 0 || static_cast<size_t>(w) >= n - off) return 0;
    off += static_cast<size_t>(w);
    return off;
}

// anchors メッセージ {"cell":"A","anchors":["0x0011","0x0012",...]} から
// アンカーアドレスを抽出する。戻り値: 抽出数 (最大 max_out)。
// 依存を増やさないため "anchors" キー以降の "0x...." トークンを走査する簡易実装。
inline size_t parseAnchorsJson(const char* json, uint16_t* out, size_t max_out) {
    const char* p = strstr(json, "\"anchors\"");
    if (p == nullptr) return 0;
    size_t count = 0;
    while (count < max_out) {
        p = strstr(p, "\"0x");
        if (p == nullptr) break;
        unsigned int v = 0;
        if (sscanf(p, "\"0x%4x\"", &v) == 1) {
            out[count++] = static_cast<uint16_t>(v);
        }
        p += 3;  // 次の探索へ ("\"0x" の分を進める)
    }
    return count;
}

}  // namespace rtls
