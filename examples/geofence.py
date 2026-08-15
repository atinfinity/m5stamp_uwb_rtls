#!/usr/bin/env python3
"""アプリケーション例: ジオフェンス(領域の入退場検知)。

指定した矩形領域へのタグの入場/退場イベントを表示する。
アプリ側で持つべき定石を含む:
  - TRACKING のみをトリガに使う(COASTING/STALE は推測位置のため保留)
  - 境界のヒステリシス(margin)でイベントのバタつきを防ぐ
  - 品質ゲート(残差が大きいエポックは無視)

使い方:
    uv run python examples/geofence.py --zone 0,0,25,25 [--margin 1.0]
"""
import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiomqtt  # noqa: E402


class Geofence:
    def __init__(self, rect: tuple[float, float, float, float], margin: float,
                 max_residual: float) -> None:
        self.rect = rect
        self.margin = margin
        self.max_residual = max_residual
        self.inside: dict[str, bool] = {}

    def _contains(self, x: float, y: float, grow: float) -> bool:
        x0, y0, x1, y1 = self.rect
        return (x0 - grow) <= x <= (x1 + grow) and (y0 - grow) <= y <= (y1 + grow)

    def update(self, tag: str, x: float, y: float) -> str | None:
        """イベント名 ('ENTER'/'EXIT') か None を返す。"""
        was_inside = self.inside.get(tag, False)
        if was_inside:
            # 退場判定は margin ぶん外側まで維持 (ヒステリシス)
            if not self._contains(x, y, self.margin):
                self.inside[tag] = False
                return "EXIT"
        else:
            if self._contains(x, y, 0.0):
                self.inside[tag] = True
                return "ENTER"
        return None


async def run(host: str, port: int, fence: Geofence) -> None:
    async with aiomqtt.Client(host, port) as client:
        await client.subscribe("rtls/tag/+/position", qos=0)
        print(f"geofence zone={fence.rect} margin={fence.margin} m — watching…")
        async for msg in client.messages:
            d = json.loads(msg.payload)
            # 定石①: 確定測位以外でトリガしない
            if d["state"] != "TRACKING":
                continue
            # 定石②: 品質ゲート (残差が大きい = 測位が怪しいエポックは無視)
            if d.get("quality", {}).get("residual_m", 0) > fence.max_residual:
                continue
            event = fence.update(d["tag"], d["x_m"], d["y_m"])
            if event:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] {event:5s} {d['tag']} at ({d['x_m']:.2f}, {d['y_m']:.2f})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--zone", default="0,0,25,25",
                    help="x0,y0,x1,y1 [m] (既定: セル A の矩形)")
    ap.add_argument("--margin", type=float, default=1.0, help="退場ヒステリシス [m]")
    ap.add_argument("--max-residual", type=float, default=0.5,
                    help="この残差 [m] を超えるエポックは無視")
    args = ap.parse_args()
    rect = tuple(float(v) for v in args.zone.split(","))
    if len(rect) != 4:
        ap.error("--zone は x0,y0,x1,y1")
    fence = Geofence(rect, args.margin, args.max_residual)
    try:
        asyncio.run(run(args.host, args.port, fence))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
