// parity_main — Python 一致試験用ハーネス (tag-design.md §10 の 2.)
//
// 使い方: parity <anchors.txt> <ranges.jsonl>
//   anchors.txt: 1 行目 "tag_height <m>"、以降 "<hex addr> <x> <y> <z> <bias_mm>"
//   ranges.jsonl: シミュレータ出力 (server/simulate.py の形式)
// 出力: 1 行 1 Position の JSONL (stdout)
//
// JSON 解析はシミュレータの固定形式のみ対象の簡易実装 (依存ゼロを優先)。
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "pipeline.hpp"

using namespace rtls_solver;

static const char* stateName(TrackState s) {
    switch (s) {
        case TrackState::TRACKING: return "TRACKING";
        case TrackState::COASTING: return "COASTING";
        case TrackState::STALE: return "STALE";
        case TrackState::LOST: return "LOST";
        default: return "INIT";
    }
}

int main(int argc, char** argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: parity <anchors.txt> <ranges.jsonl>\n");
        return 1;
    }

    // ---- アンカー表の読込 ----
    FILE* fa = fopen(argv[1], "r");
    if (fa == nullptr) {
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    AnchorInfo anchors[kMaxAnchorTable];
    int n_anchors = 0;
    float tag_height = 1.0f;
    char line[512];
    while (fgets(line, sizeof(line), fa) != nullptr) {
        float th;
        if (sscanf(line, "tag_height %f", &th) == 1) {
            tag_height = th;
            continue;
        }
        unsigned int addr;
        float x, y, z;
        int bias;
        if (n_anchors < kMaxAnchorTable &&
            sscanf(line, "%x %f %f %f %d", &addr, &x, &y, &z, &bias) == 5) {
            anchors[n_anchors++] = {static_cast<uint16_t>(addr), x, y, z, bias};
        }
    }
    fclose(fa);

    // ---- タグ別パイプライン (最大 8 タグ、出現順に割当) ----
    constexpr int kMaxTags = 8;
    uint16_t tag_addrs[kMaxTags];
    TagPipeline* pipes[kMaxTags] = {};
    int n_tags = 0;

    FILE* fr = fopen(argv[2], "r");
    if (fr == nullptr) {
        fprintf(stderr, "cannot open %s\n", argv[2]);
        return 1;
    }
    char buf[2048];
    while (fgets(buf, sizeof(buf), fr) != nullptr) {
        // json.dumps の既定形式はコロン後に空白が入る。値に空白を含むフィールドは
        // 無いため、空白を除去してから固定形式として解析する。
        {
            char* w = buf;
            for (const char* rd = buf; *rd != '\0'; rd++) {
                if (*rd != ' ' && *rd != '\t') {
                    *w++ = *rd;
                }
            }
            *w = '\0';
        }
        unsigned int tag;
        unsigned long seq;
        unsigned long long t_ms, recv_ms;
        const char* p = strstr(buf, "\"tag\":\"0x");
        if (p == nullptr || sscanf(p, "\"tag\":\"0x%4x\"", &tag) != 1) continue;
        p = strstr(buf, "\"seq\":");
        if (p == nullptr || sscanf(p, "\"seq\":%lu", &seq) != 1) continue;
        p = strstr(buf, "\"t_ms\":");
        if (p == nullptr || sscanf(p, "\"t_ms\":%llu", &t_ms) != 1) continue;
        p = strstr(buf, "\"recv_ms\":");
        if (p == nullptr || sscanf(p, "\"recv_ms\":%llu", &recv_ms) != 1) {
            recv_ms = t_ms;
        }

        RangeMeas meas[kMaxRanges];
        int n_meas = 0;
        p = strstr(buf, "\"ranges\":");
        while (p != nullptr && n_meas < kMaxRanges) {
            p = strstr(p, "{\"a\":\"0x");
            if (p == nullptr) break;
            unsigned int a;
            long d_mm;
            char okbuf[8] = {};
            if (sscanf(p, "{\"a\":\"0x%4x\",\"d_mm\":%ld,\"ok\":%5[a-z]", &a, &d_mm, okbuf) == 3) {
                meas[n_meas++] = {static_cast<uint16_t>(a), static_cast<int32_t>(d_mm),
                                  strncmp(okbuf, "true", 4) == 0};
            }
            p += 6;
        }

        // タグ → パイプライン
        int idx = -1;
        for (int i = 0; i < n_tags; i++) {
            if (tag_addrs[i] == tag) {
                idx = i;
                break;
            }
        }
        if (idx < 0) {
            if (n_tags >= kMaxTags) continue;
            idx = n_tags++;
            tag_addrs[idx] = static_cast<uint16_t>(tag);
            pipes[idx] = new TagPipeline(anchors, n_anchors, tag_height);
        }

        PosOut out = pipes[idx]->process(static_cast<uint32_t>(seq), t_ms, recv_ms, meas, n_meas);
        if (out.valid) {
            printf("{\"tag\":\"0x%04X\",\"t_ms\":%llu,\"x_m\":%.6f,\"y_m\":%.6f,"
                   "\"state\":\"%s\",\"n_used\":%d}\n",
                   tag, static_cast<unsigned long long>(out.t_ms), double(out.x), double(out.y),
                   stateName(out.state), out.n_used);
        }
    }
    fclose(fr);
    for (int i = 0; i < n_tags; i++) {
        delete pipes[i];
    }
    return 0;
}
