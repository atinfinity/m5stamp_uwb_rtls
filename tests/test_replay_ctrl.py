"""リプレイ操作 (server/replay_ctrl.py) のテスト。実機・ブローカー不要。"""
import asyncio
import json

import pytest

from server.replay_ctrl import ReplayController
from server.simulate import simulate


class FakeHub:
    def __init__(self):
        self.messages = []

    async def broadcast(self, m):
        self.messages.append(m)


@pytest.fixture()
def log_file(config, tmp_path):
    lines = [json.dumps(m) for m, _ in simulate(config, duration_s=20.0, seed=6)]
    p = tmp_path / "ranges-test.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_list_and_resolve(config, tmp_path, log_file):
    hub = FakeHub()
    rc = ReplayController(config, hub, [tmp_path])
    logs = rc.list_logs()
    assert [l["name"] for l in logs] == ["ranges-test.jsonl"]
    # 一覧に無い名前 (パストラバーサル含む) は開始できない
    assert asyncio.run(rc.start("../secrets.jsonl", 0)) is False
    assert asyncio.run(rc.start("unknown.jsonl", 0)) is False


def test_full_playback_broadcasts_positions(config, tmp_path, log_file):
    hub = FakeHub()
    rc = ReplayController(config, hub, [tmp_path])

    async def run():
        assert await rc.start("ranges-test.jsonl", speed=0) is True
        for _ in range(200):
            if rc.state == "finished":
                break
            await asyncio.sleep(0.05)
        assert rc.state == "finished"

    asyncio.run(run())
    positions = [m for m in hub.messages if m.get("type") == "position"]
    statuses = [m for m in hub.messages if m.get("type") == "replay"]
    assert len(positions) > 80                      # 20s × 2Hz × 3タグ ≈ 120 エポック
    assert all(p["src"] == "replay" for p in positions)
    assert statuses[-1]["state"] == "finished"
    assert rc.idx == rc.total


def test_pause_resume_stop(config, tmp_path, log_file):
    hub = FakeHub()
    rc = ReplayController(config, hub, [tmp_path])

    async def run():
        await rc.start("ranges-test.jsonl", speed=1.0)  # 実時間 → 途中で操作できる
        await asyncio.sleep(0.3)
        rc.pause()
        assert rc.state == "paused"
        idx_at_pause = rc.idx
        await asyncio.sleep(0.5)
        assert rc.idx <= idx_at_pause + 1  # 一時停止中は進まない
        rc.resume()
        assert rc.state == "playing"
        await asyncio.sleep(0.3)
        assert rc.idx > idx_at_pause
        await rc.stop()
        assert rc.state == "idle" and rc.file is None

    asyncio.run(run())
