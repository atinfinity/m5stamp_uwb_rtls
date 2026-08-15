"""tools/publish_config.py の canonical 形式テスト (Issue #28)。

タグ側パーサ (rtls_config_msg.h) はキー順固定の canonical 形式を前提とする。
このテストが通る形式が firmware/test_native/test_rtls_config.cpp のサンプルと
一致していること (両者で同じ仕様を固定する)。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import publish_config as pc  # noqa: E402


def test_anchors_payload_is_canonical(config):
    payload = pc.canonical_anchors_payload(config, version=7)
    # 有効な JSON である
    d = json.loads(payload)
    assert d["version"] == 7
    assert len(d["anchors"]) == len(config.anchors)
    assert len(d["cells"]) == len(config.cells)
    # タグ側パーサが前提とするキー順 (anchors → cells、エントリ内は x,y,z,bias_mm)
    assert payload.index('"anchors"') < payload.index('"cells"')
    assert re.search(
        r'"0x[0-9A-F]{4}":\{"x":[-\d.]+,"y":[-\d.]+,"z":[-\d.]+,"bias_mm":-?\d+\}',
        payload)
    assert re.search(
        r'"[A-Za-z0-9_]+":\{"rect":\[[-\d.,]+\],"anchors":\["0x[0-9A-F]{4}"',
        payload)
    # 空白を含まない (タグ側は stripJsonSpaces 前提だが、余計な差異を作らない)
    assert " " not in payload


def test_tuning_payload_is_canonical(config):
    payload = pc.canonical_tuning_payload(config, version=9)
    d = json.loads(payload)
    assert d["version"] == 9
    expected = {"version", "max_age_ms", "v_max_ms", "gate_margin_m",
                "residual_gate_m", "sigma_a", "sigma_m_floor", "stale_sec",
                "lost_sec", "handover_margin_m"}
    assert set(d) == expected
    assert " " not in payload


def test_payload_fits_tag_buffers(config):
    """タグ側の受信バッファ (2048 byte) に収まること。"""
    assert len(pc.canonical_anchors_payload(config, 1)) < 2048
    assert len(pc.canonical_tuning_payload(config, 1)) < 384