// rtls_config_msg.h — B案 タグ上計算のための設定メッセージ処理 (Issue #28)
//   - rtls/config/anchors, rtls/config/tuning の canonical JSON パーサ
//   - オンボードセル選択 (server/cells.py と同じヒステリシス)
//   - UART 30 byte フレーム (tag-design.md §7) / position JSON ビルダ
// Arduino 非依存・外部ライブラリ非依存 (ホストでネイティブテスト可能)。
//
// canonical JSON は tools/publish_config.py が生成する形式のみを対象とする
// (キー順固定)。パース前に stripJsonSpaces() で空白を除去すること。
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace rtls {

struct AnchorDef {
    uint16_t addr;
    float x, y, z;
    int32_t bias_mm;
};

constexpr int kMaxCellAnchors = 6;
constexpr int kMaxCells       = 8;
constexpr int kMaxCfgAnchors  = 16;

struct CellDef {
    char name[8];
    float rect[4];  // x0, y0, x1, y1
    uint16_t anchors[kMaxCellAnchors];
    int n_anchors;
};

struct TuningDef {
    float max_age_ms        = 500;
    float v_max_ms          = 2.0f;
    float gate_margin_m     = 0.6f;
    float residual_gate_m   = 0.5f;
    float sigma_a           = 1.0f;
    float sigma_m_floor     = 0.15f;
    float stale_sec         = 2.0f;
    float lost_sec          = 10.0f;
    float handover_margin_m = 2.0f;
};

struct AnchorsConfig {
    uint32_t version = 0;
    float tag_height_m = 1.0f;
    AnchorDef anchors[kMaxCfgAnchors];
    int n_anchors = 0;
    CellDef cells[kMaxCells];
    int n_cells = 0;
};

// JSON 中の空白を除去する (値に空白を含むフィールドは無い前提)
inline void stripJsonSpaces(char* s) {
    char* w = s;
    for (const char* r = s; *r != '\0'; r++) {
        if (*r != ' ' && *r != '\t' && *r != '\n' && *r != '\r') {
            *w++ = *r;
        }
    }
    *w = '\0';
}

namespace detail {

inline bool findNumber(const char* json, const char* key, float* out) {
    char pat[48];
    snprintf(pat, sizeof(pat), "\"%s\":", key);
    const char* p = strstr(json, pat);
    if (p == nullptr) return false;
    return sscanf(p + strlen(pat), "%f", out) == 1;
}

}  // namespace detail

// rtls/config/anchors のパース。成功時 true。
// 形式: {"version":3,"tag_height_m":1.0,
//        "anchors":{"0x0010":{"x":0.0,"y":0.0,"z":2.2,"bias_mm":0},...},
//        "cells":{"A":{"rect":[0,0,25,25],"anchors":["0x0010",...]},...}}
inline bool parseAnchorsConfig(const char* json, AnchorsConfig* out) {
    float ver = 0;
    if (!detail::findNumber(json, "version", &ver)) return false;
    out->version = (uint32_t)ver;
    detail::findNumber(json, "tag_height_m", &out->tag_height_m);

    const char* anchorsPos = strstr(json, "\"anchors\":{");
    const char* cellsPos   = strstr(json, "\"cells\":{");
    if (anchorsPos == nullptr || cellsPos == nullptr || cellsPos < anchorsPos) return false;

    // ---- anchors (cells の手前まで走査) ----
    out->n_anchors = 0;
    const char* p = anchorsPos;
    while (out->n_anchors < kMaxCfgAnchors) {
        p = strstr(p, "\"0x");
        if (p == nullptr || p >= cellsPos) break;
        unsigned int addr;
        float x, y, z;
        int bias;
        if (sscanf(p, "\"0x%4x\":{\"x\":%f,\"y\":%f,\"z\":%f,\"bias_mm\":%d}",
                   &addr, &x, &y, &z, &bias) == 5) {
            out->anchors[out->n_anchors++] = {(uint16_t)addr, x, y, z, bias};
        }
        p += 3;
    }
    if (out->n_anchors == 0) return false;

    // ---- cells ----
    out->n_cells = 0;
    p = cellsPos + strlen("\"cells\":{");
    while (out->n_cells < kMaxCells) {
        // 次のセル名: "NAME":{"rect":[
        if (*p != '"') break;
        CellDef* c = &out->cells[out->n_cells];
        const char* nameEnd = strchr(p + 1, '"');
        if (nameEnd == nullptr) break;
        size_t nlen = (size_t)(nameEnd - p - 1);
        if (nlen == 0 || nlen >= sizeof(c->name)) return false;
        memcpy(c->name, p + 1, nlen);
        c->name[nlen] = '\0';

        const char* rect = strstr(nameEnd, "\"rect\":[");
        if (rect == nullptr ||
            sscanf(rect, "\"rect\":[%f,%f,%f,%f]",
                   &c->rect[0], &c->rect[1], &c->rect[2], &c->rect[3]) != 4) {
            return false;
        }
        const char* alist = strstr(rect, "\"anchors\":[");
        const char* aend  = alist ? strchr(alist, ']') : nullptr;
        if (alist == nullptr || aend == nullptr) return false;
        c->n_anchors = 0;
        const char* ap = alist;
        while (c->n_anchors < kMaxCellAnchors) {
            ap = strstr(ap, "\"0x");
            if (ap == nullptr || ap > aend) break;
            unsigned int addr;
            if (sscanf(ap, "\"0x%4x\"", &addr) == 1) {
                c->anchors[c->n_anchors++] = (uint16_t)addr;
            }
            ap += 3;
        }
        if (c->n_anchors < 3) return false;  // 3 台未満のセルは解算不可
        out->n_cells++;
        // 次のセルへ: '}' の後のカンマ→'"'
        p = strchr(aend, '}');
        if (p == nullptr) break;
        p++;
        if (*p == ',') p++;
    }
    return out->n_cells > 0;
}

// rtls/config/tuning のパース (存在するキーのみ上書き)。version 必須。
inline bool parseTuningConfig(const char* json, TuningDef* t, uint32_t* version) {
    float ver = 0;
    if (!detail::findNumber(json, "version", &ver)) return false;
    *version = (uint32_t)ver;
    detail::findNumber(json, "max_age_ms", &t->max_age_ms);
    detail::findNumber(json, "v_max_ms", &t->v_max_ms);
    detail::findNumber(json, "gate_margin_m", &t->gate_margin_m);
    detail::findNumber(json, "residual_gate_m", &t->residual_gate_m);
    detail::findNumber(json, "sigma_a", &t->sigma_a);
    detail::findNumber(json, "sigma_m_floor", &t->sigma_m_floor);
    detail::findNumber(json, "stale_sec", &t->stale_sec);
    detail::findNumber(json, "lost_sec", &t->lost_sec);
    detail::findNumber(json, "handover_margin_m", &t->handover_margin_m);
    return true;
}

// ---- オンボードセル選択 (server/cells.py と同じヒステリシス, tag-design §5) ----

inline bool cellContains(const CellDef& c, float x, float y, float grow) {
    return (c.rect[0] - grow) <= x && x <= (c.rect[2] + grow) &&
           (c.rect[1] - grow) <= y && y <= (c.rect[3] + grow);
}

// current: 現在のセル index (-1 = 未確定)。戻り値: 新しい index。
inline int selectCell(const CellDef* cells, int n, float x, float y, int current,
                      float margin) {
    if (current >= 0 && current < n && cellContains(cells[current], x, y, margin)) {
        return current;
    }
    for (int i = 0; i < n; i++) {
        if (cellContains(cells[i], x, y, 0.0f)) return i;
    }
    // どのセルにも入らない: 中心が最も近いセル
    int best = 0;
    float bestD = 1e30f;
    for (int i = 0; i < n; i++) {
        const float cx = (cells[i].rect[0] + cells[i].rect[2]) / 2;
        const float cy = (cells[i].rect[1] + cells[i].rect[3]) / 2;
        const float d = (cx - x) * (cx - x) + (cy - y) * (cy - y);
        if (d < bestD) {
            bestD = d;
            best = i;
        }
    }
    return best;
}

// ---- UART バイナリフレーム (tag-design.md §7, 30 byte, little-endian) ----

constexpr size_t kUartFrameLen = 30;

inline void buildUartFrame(uint8_t out[kUartFrameLen], uint8_t tag_id, uint8_t state,
                           uint32_t t_ms, float x, float y, float vx, float vy,
                           float residual, uint8_t n_used) {
    out[0] = 0xB5;
    out[1] = 0x50;
    out[2] = tag_id;
    out[3] = state;
    memcpy(&out[4], &t_ms, 4);
    memcpy(&out[8], &x, 4);
    memcpy(&out[12], &y, 4);
    memcpy(&out[16], &vx, 4);
    memcpy(&out[20], &vy, 4);
    memcpy(&out[24], &residual, 4);
    out[28] = n_used;
    uint8_t sum = 0;
    for (size_t i = 0; i < kUartFrameLen - 1; i++) sum ^= out[i];
    out[29] = sum;
}

// ---- position JSON (サーバー出力と互換 + src:"tag", application-guide.md §2) ----

inline size_t buildPositionJson(char* buf, size_t n, uint16_t tag, uint64_t t_ms,
                                float x, float y, float vx, float vy, int n_used,
                                float residual, const char* state, const char* cell) {
    int w = snprintf(buf, n,
                     "{\"tag\":\"0x%04X\",\"t_ms\":%llu,\"x_m\":%.3f,\"y_m\":%.3f,"
                     "\"vx_ms\":%.3f,\"vy_ms\":%.3f,"
                     "\"quality\":{\"n_anchors\":%d,\"residual_m\":%.3f},"
                     "\"cell\":\"%s\",\"state\":\"%s\",\"src\":\"tag\"}",
                     tag, (unsigned long long)t_ms, (double)x, (double)y, (double)vx,
                     (double)vy, n_used, (double)residual, cell, state);
    return (w > 0 && (size_t)w < n) ? (size_t)w : 0;
}

}  // namespace rtls
