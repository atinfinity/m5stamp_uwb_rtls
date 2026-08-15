#include "config_store.h"

#include <Preferences.h>

namespace cfgstore {

static Preferences prefs;

void begin() {
    prefs.begin("rtls", /*readOnly=*/false);
}

Mode mode() {
    return static_cast<Mode>(prefs.getUChar("mode", static_cast<uint8_t>(Mode::HYBRID)));
}

void setMode(Mode m) {
    prefs.putUChar("mode", static_cast<uint8_t>(m));
}

const char* modeName(Mode m) {
    switch (m) {
        case Mode::STANDALONE: return "STANDALONE";
        case Mode::QUIET: return "QUIET";
        default: return "HYBRID";
    }
}

bool parseMode(const char* s, Mode* out) {
    if (strcasecmp(s, "HYBRID") == 0) { *out = Mode::HYBRID; return true; }
    if (strcasecmp(s, "STANDALONE") == 0) { *out = Mode::STANDALONE; return true; }
    if (strcasecmp(s, "QUIET") == 0) { *out = Mode::QUIET; return true; }
    return false;
}

bool loadAnchors(String* json, uint32_t* version) {
    *version = prefs.getULong("anch_ver", 0);
    *json = prefs.getString("anch_json", "");
    return *version > 0 && json->length() > 0;
}

void saveAnchors(const char* json, uint32_t version) {
    prefs.putString("anch_json", json);
    prefs.putULong("anch_ver", version);
}

bool loadTuning(String* json, uint32_t* version) {
    *version = prefs.getULong("tune_ver", 0);
    *json = prefs.getString("tune_json", "");
    return *version > 0 && json->length() > 0;
}

void saveTuning(const char* json, uint32_t version) {
    prefs.putString("tune_json", json);
    prefs.putULong("tune_ver", version);
}

}  // namespace cfgstore
