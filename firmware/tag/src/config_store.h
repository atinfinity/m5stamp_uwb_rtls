// config_store — NVS 永続化 (Issue #28 / tag-design.md §5)
// rtls/config/# で受けた設定 (raw JSON + version) と動作モードを保存し、
// Wi-Fi 断・再起動後も NVS から復元して動作継続できるようにする。
#pragma once

#include <Arduino.h>

namespace cfgstore {

// 動作モード (tag-design.md §2)
enum class Mode : uint8_t { HYBRID = 0, STANDALONE = 1, QUIET = 2 };

void begin();

Mode mode();
void setMode(Mode m);
const char* modeName(Mode m);
bool parseMode(const char* s, Mode* out);

bool loadAnchors(String* json, uint32_t* version);
void saveAnchors(const char* json, uint32_t version);
bool loadTuning(String* json, uint32_t* version);
void saveTuning(const char* json, uint32_t version);

}  // namespace cfgstore
