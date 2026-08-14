#!/usr/bin/env python3
"""仮想タグ — シミュレータの ranges を実時間で MQTT へ publish する。

実機タグの代わりにブローカー → サーバー → UI の本番経路を通す結合試験用。
t_ms は実時刻(壁時計)で置き換えるため、サーバーの鮮度チェックも通る。

使い方:
    python tools/virtual_tag.py --config server/config.yaml [--rate-hz 2]
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiomqtt  # noqa: E402

from server.config import load_config  # noqa: E402
from server.simulate import SimParams, simulate  # noqa: E402


async def run(config_path: str, rate_hz: float, duration_s: float) -> None:
    config = load_config(config_path)
    params = SimParams(rate_hz=rate_hz)
    n_tags = len(config.tags)
    epoch_s = 1.0 / rate_hz
    slot_s = epoch_s / max(n_tags, 1)

    gen = simulate(config, duration_s, seed=int(time.time()) % 10000, params=params)
    async with aiomqtt.Client(config.mqtt.host, config.mqtt.port) as client:
        print(f"virtual tags: {n_tags} tags at {rate_hz} Hz -> "
              f"mqtt://{config.mqtt.host}:{config.mqtt.port}")
        sent = 0
        for msg, _truth in gen:
            # シミュレータの合成時刻を実時刻へ差し替える
            msg = dict(msg)
            msg.pop("recv_ms", None)
            msg["t_ms"] = int(time.time() * 1000)
            topic = f"rtls/tag/{msg['tag']}/ranges"
            await client.publish(topic, json.dumps(msg), qos=0)
            sent += 1
            if sent % (n_tags * int(rate_hz) * 10 or 1) == 0:
                print(f"sent {sent} epochs")
            await asyncio.sleep(slot_s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="server/config.yaml")
    ap.add_argument("--rate-hz", type=float, default=2.0)
    ap.add_argument("--duration-s", type=float, default=3600.0)
    args = ap.parse_args()
    try:
        asyncio.run(run(args.config, args.rate_hz, args.duration_s))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
