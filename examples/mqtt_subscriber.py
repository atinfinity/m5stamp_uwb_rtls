#!/usr/bin/env python3
"""最小のアプリケーション例: 測位結果 (position) を購読して表示する。

使い方:
    uv run python examples/mqtt_subscriber.py [--host 127.0.0.1] [--port 1883]

実機がなくても、development.md §4 の手順(mosquitto + server + virtual_tag)で
そのまま動く。アプリは rtls/tag/+/position を購読するだけでよく、
サーバー・タグ側に一切手を入れずに追加できる。
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiomqtt  # noqa: E402


async def run(host: str, port: int) -> None:
    async with aiomqtt.Client(host, port) as client:
        await client.subscribe("rtls/tag/+/position", qos=0)
        print("subscribed to rtls/tag/+/position")
        async for msg in client.messages:
            d = json.loads(msg.payload)
            q = d.get("quality", {})
            print(f"{d['tag']}  ({d['x_m']:6.2f}, {d['y_m']:6.2f}) m  "
                  f"cell={d['cell']}  {d['state']:8s}  "
                  f"res={q.get('residual_m', 0):.2f} m  n={q.get('n_anchors', 0)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    args = ap.parse_args()
    try:
        asyncio.run(run(args.host, args.port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
