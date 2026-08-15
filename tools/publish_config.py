#!/usr/bin/env python3
"""B案 タグ向け設定配布 (Issue #28 / tag-design.md §5, §8)。

server/config.yaml からアンカー座標・セル表・tuning を canonical JSON にして
rtls/config/anchors と rtls/config/tuning へ retained publish する。
タグは version が上がったときだけ NVS に保存して反映する。

canonical 形式 (キー順固定) はタグ側パーサ (rtls_config_msg.h) が前提とする —
このツール以外から publish しないこと。

使い方:
    uv run python tools/publish_config.py [--config server/config.yaml] [--version N]
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiomqtt  # noqa: E402

from server.config import load_config, parse_addr  # noqa: E402


def canonical_anchors_payload(config, version: int) -> str:
    anchors = ",".join(
        f'"0x{parse_addr(k):04X}":{{"x":{a.x},"y":{a.y},"z":{a.z},"bias_mm":{a.bias_mm}}}'
        for k, a in config.anchors.items())
    cells = ",".join(
        f'"{name}":{{"rect":[{c.rect[0]},{c.rect[1]},{c.rect[2]},{c.rect[3]}],'
        f'"anchors":[{",".join(f_addr(a) for a in c.anchors)}]}}'
        for name, c in config.cells.items())
    return (f'{{"version":{version},"tag_height_m":{config.floor.tag_height_m},'
            f'"anchors":{{{anchors}}},"cells":{{{cells}}}}}')


def f_addr(a: str) -> str:
    return f'"0x{parse_addr(a):04X}"'


def canonical_tuning_payload(config, version: int) -> str:
    t = config.tuning
    return json.dumps({
        "version": version,
        "max_age_ms": t.max_age_ms, "v_max_ms": t.v_max_ms,
        "gate_margin_m": t.gate_margin_m, "residual_gate_m": t.residual_gate_m,
        "sigma_a": t.sigma_a, "sigma_m_floor": t.sigma_m_floor,
        "stale_sec": t.stale_sec, "lost_sec": t.lost_sec,
        "handover_margin_m": t.handover_margin_m,
    }, separators=(",", ":"))


async def publish(config_path: str, version: int) -> None:
    config = load_config(config_path)
    anchors = canonical_anchors_payload(config, version)
    tuning = canonical_tuning_payload(config, version)
    async with aiomqtt.Client(config.mqtt.host, config.mqtt.port) as client:
        await client.publish("rtls/config/anchors", anchors, qos=1, retain=True)
        await client.publish("rtls/config/tuning", tuning, qos=1, retain=True)
    print(f"published version={version}")
    print(f"  rtls/config/anchors: {len(anchors)} bytes "
          f"({len(config.anchors)} anchors, {len(config.cells)} cells)")
    print(f"  rtls/config/tuning : {len(tuning)} bytes")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="server/config.yaml")
    ap.add_argument("--version", type=int, default=int(time.time()),
                    help="設定バージョン (既定: 現在の UNIX 秒 — 単調増加)")
    args = ap.parse_args()
    asyncio.run(publish(args.config, args.version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
