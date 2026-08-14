"""測位サーバー本体 (server-design.md §3, §7, §11)。

MQTT 受信 → recorder → pipeline → position 出版 / WebSocket 配信 /
セルハンドオーバー (anchors retained 出版) を単一プロセス asyncio で行う。

使い方:
    python -m server.app --config server/config.yaml [--http-port 8000]
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import time

import aiomqtt
import uvicorn

from server.cells import CellManager
from server.config import RtlsConfig, load_config
from server.models import Position, RangeSet
from server.monitor import Monitor
from server.positioning.pipeline import TagPipeline
from server.recorder import JsonlRecorder
from server.web.api import Hub, create_app

log = logging.getLogger("rtls")


def now_ms() -> int:
    return int(time.time() * 1000)


class RtlsServer:
    def __init__(self, config: RtlsConfig, log_dir: str = "logs") -> None:
        self.config = config
        self.cells = CellManager(config)
        self.pipelines = {t: TagPipeline(t, config, self.cells) for t in config.tag_addrs()}
        self.recorder = JsonlRecorder(log_dir)
        self.monitor = Monitor()
        self.hub = Hub()
        self.latest: dict[int, Position] = {}
        self._published_cell: dict[int, str] = {}
        self._client: aiomqtt.Client | None = None

    # ---- MQTT ----

    async def run_mqtt(self) -> None:
        backoff = 1.0
        while True:
            try:
                async with aiomqtt.Client(self.config.mqtt.host, self.config.mqtt.port) as client:
                    self._client = client
                    backoff = 1.0
                    log.info("mqtt connected %s:%d", self.config.mqtt.host, self.config.mqtt.port)
                    await client.subscribe("rtls/tag/+/ranges", qos=0)
                    async for message in client.messages:
                        await self._on_ranges(bytes(message.payload))
            except aiomqtt.MqttError as e:
                self._client = None
                log.warning("mqtt disconnected (%s); retry in %.0fs", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def _on_ranges(self, payload: bytes) -> None:
        recv = now_ms()
        self.recorder.append(payload, recv)
        try:
            rs = RangeSet.from_json(payload, recv_ms=recv)
        except (ValueError, KeyError, json.JSONDecodeError):
            self.monitor.on_invalid(-1)
            return
        self.monitor.on_received(rs.tag, rs.t_ms, recv)
        for r in rs.ranges:
            self.monitor.on_anchor_result(r.anchor, r.ok)

        pl = self.pipelines.get(rs.tag)
        if pl is None:
            self.monitor.on_invalid(rs.tag)
            return
        if recv - rs.t_ms > self.config.tuning.max_age_ms:
            self.monitor.on_stale(rs.tag)
        pos = pl.process(rs)
        if pos is None:
            return
        self.latest[rs.tag] = pos
        await self._publish_position(pos)
        await self.hub.broadcast(json.loads(pos.to_json()) | {"type": "position"})
        await self._maybe_handover(rs.tag, pos.cell)

    async def _publish_position(self, pos: Position) -> None:
        if self._client is None:
            return
        with contextlib.suppress(aiomqtt.MqttError):
            await self._client.publish(
                f"rtls/tag/0x{pos.tag:04X}/position", pos.to_json(), qos=0)

    async def _maybe_handover(self, tag: int, cell: str) -> None:
        """セルが変わったときのみ担当アンカーリストを retained 出版する。"""
        if not cell or self._published_cell.get(tag) == cell or self._client is None:
            return
        anchors = [f"0x{a:04X}" for a in self.cells.anchors_of(cell)]
        payload = json.dumps({"cell": cell, "anchors": anchors})
        with contextlib.suppress(aiomqtt.MqttError):
            await self._client.publish(
                f"rtls/tag/0x{tag:04X}/anchors", payload, qos=1, retain=True)
            self._published_cell[tag] = cell
            log.info("handover tag=0x%04X -> cell %s", tag, cell)


async def amain(config_path: str, http_port: int, log_dir: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(config_path)
    server = RtlsServer(config, log_dir)

    app = create_app(server)
    uv_config = uvicorn.Config(app, host="0.0.0.0", port=http_port, log_level="warning")
    uv_server = uvicorn.Server(uv_config)

    await asyncio.gather(server.run_mqtt(), uv_server.serve())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="server/config.yaml")
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--log-dir", default="logs")
    args = ap.parse_args()
    asyncio.run(amain(args.config, args.http_port, args.log_dir))


if __name__ == "__main__":
    main()
