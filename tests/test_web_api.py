"""Web API のテスト (server-design.md §9)。MQTT ブローカー不要。"""
import asyncio
import json

import pytest
from starlette.testclient import TestClient

from server.app import RtlsServer
from server.web.api import create_app


@pytest.fixture()
def server(config, tmp_path):
    return RtlsServer(config, log_dir=str(tmp_path / "logs"))


@pytest.fixture()
def client(server):
    return TestClient(create_app(server))


def make_ranges_payload(config, tag="0x0001", seq=1, t_ms=None):
    import time

    t_ms = t_ms or int(time.time() * 1000)
    cell = config.cells["A"]
    anchors = config.anchor_by_addr()
    ranges = []
    for a_str in cell.anchors:
        addr = int(a_str, 0)
        a = anchors[addr]
        d = ((a.x - 10) ** 2 + (a.y - 8) ** 2 + (a.z - 1.0) ** 2) ** 0.5
        ranges.append({"a": a_str, "d_mm": int(d * 1000), "ok": True})
    return json.dumps({"tag": tag, "seq": seq, "t_ms": t_ms, "ranges": ranges}), t_ms


def test_floor_endpoint(client, config):
    d = client.get("/api/floor").json()
    assert d["width_m"] == config.floor.width_m
    assert set(d["anchors"]) == set(config.anchors)
    assert set(d["cells"]) == set(config.cells)


def test_ranges_to_tags_endpoint(server, client, config):
    payload, _ = make_ranges_payload(config)
    asyncio.run(server._on_ranges(payload.encode()))
    tags = client.get("/api/tags").json()
    assert "0x0001" in tags
    t = tags["0x0001"]
    assert abs(t["x_m"] - 10) < 0.1 and abs(t["y_m"] - 8) < 0.1
    assert t["state"] == "TRACKING"
    # position JSON に品質情報が載る
    pos = server.latest[1]
    d = json.loads(pos.to_json())
    assert d["anchors_used"] == ["0x0010", "0x0011", "0x0013", "0x0014"]
    assert d["anchors_rejected"] == []


def test_stats_endpoint(server, client, config):
    payload, _ = make_ranges_payload(config)
    asyncio.run(server._on_ranges(payload.encode()))
    stats = client.get("/api/stats").json()
    assert stats["tags"]["0x0001"]["received"] == 1
    assert stats["anchors"]["0x0010"]["n"] == 1


def test_truth_forwarding(server):
    received = []

    class FakeWs:
        async def send_json(self, m):
            received.append(m)

    async def run():
        await server.hub.add(FakeWs())
        await server._on_truth(json.dumps(
            {"tag": "0x0001", "t_ms": 123, "x": 1.5, "y": 2.5}).encode())
        await server._on_truth(b"broken json")  # 不正データは無視される

    asyncio.run(run())
    assert received == [{"type": "truth", "tag": "0x0001", "t_ms": 123,
                         "x_m": 1.5, "y_m": 2.5}]


def test_stats_broadcast(server, config):
    received = []

    class FakeWs:
        async def send_json(self, m):
            received.append(m)

    async def run():
        payload, _ = make_ranges_payload(config)
        await server._on_ranges(payload.encode())
        await server.hub.add(FakeWs())
        task = asyncio.create_task(server.run_stats_broadcast(interval_s=0.01))
        await asyncio.sleep(0.05)
        task.cancel()

    asyncio.run(run())
    stats_msgs = [m for m in received if m.get("type") == "stats"]
    assert stats_msgs
    assert stats_msgs[0]["tags"]["0x0001"]["received"] == 1


def test_websocket_connects(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text("ping")  # keepalive 経路が例外なく通ること
