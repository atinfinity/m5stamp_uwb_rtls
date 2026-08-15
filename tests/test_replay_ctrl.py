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
    lines, truths = [], []
    for m, t in simulate(config, duration_s=20.0, seed=6):
        lines.append(json.dumps(m))
        truths.append(json.dumps(t))
    p = tmp_path / "ranges-test.jsonl"
    p.write_text("\n".join(lines) + "\n")
    (tmp_path / "truth-test.jsonl").write_text("\n".join(truths) + "\n")
    return p


def test_list_and_resolve(config, tmp_path, log_file):
    hub = FakeHub()
    rc = ReplayController(config, hub, [tmp_path])
    logs = {l["name"]: l["kind"] for l in rc.list_logs()}
    # 中身で種別が判定される (ファイル名規約に依存しない)
    assert logs == {"ranges-test.jsonl": "ranges", "truth-test.jsonl": "truth"}
    # 一覧に無い名前 (パストラバーサル含む) は開始できない
    assert asyncio.run(rc.start("../secrets.jsonl", 0)) is False
    assert asyncio.run(rc.start("unknown.jsonl", 0)) is False
    # 種別の取り違えは拒否: 真値ログを測距ログとして再生できない
    assert asyncio.run(rc.start("truth-test.jsonl", 0)) is False
    # 測距ログを真値ログとして指定できない
    assert asyncio.run(rc.start("ranges-test.jsonl", 0,
                                truth_name="ranges-test.jsonl")) is False


def test_full_playback_broadcasts_positions(config, tmp_path, log_file):
    hub = FakeHub()
    rc = ReplayController(config, hub, [tmp_path])

    async def run():
        assert await rc.start("ranges-test.jsonl", speed=0,
                              truth_name="truth-test.jsonl") is True
        for _ in range(200):
            if rc.state == "finished":
                break
            await asyncio.sleep(0.05)
        assert rc.state == "finished"

    asyncio.run(run())
    positions = [m for m in hub.messages if m.get("type") == "position"]
    truths = [m for m in hub.messages if m.get("type") == "truth"]
    statuses = [m for m in hub.messages if m.get("type") == "replay"]
    assert len(positions) > 80                      # 20s × 2Hz × 3タグ ≈ 120 エポック
    assert all(p["src"] == "replay" for p in positions)
    # 真値ログ指定時は全エポックぶんの truth が流れる (誤差ヒートマップ用)
    assert len(truths) == rc.total
    # 各 position の直前に同じ (tag, t_ms) の truth が流れている
    seen = set()
    for m in hub.messages:
        if m.get("type") == "truth":
            seen.add((m["tag"], m["t_ms"]))
        elif m.get("type") == "position":
            assert (m["tag"], m["t_ms"]) in seen
    assert statuses[-1]["state"] == "finished"
    assert rc.idx == rc.total


def test_obstacle_meta_broadcast(config, tmp_path):
    """メタ行付きログの再生で遮蔽壁が配信され、メタ無しでは空で上書きされる。"""
    lines = [json.dumps({"meta": {"obstacles": [[24, 15, 26, 35]]}})]
    lines += [json.dumps(m) for m, _ in simulate(config, duration_s=5.0, seed=2)]
    (tmp_path / "with-meta.jsonl").write_text("\n".join(lines) + "\n")
    (tmp_path / "no-meta.jsonl").write_text(lines[1] + "\n")

    hub = FakeHub()
    rc = ReplayController(config, hub, [tmp_path])

    async def run(name):
        await rc.start(name, speed=0)
        for _ in range(100):
            if rc.state == "finished":
                break
            await asyncio.sleep(0.05)

    asyncio.run(run("with-meta.jsonl"))
    obs = [m for m in hub.messages if m.get("type") == "obstacles"]
    assert obs[-1]["obstacles"] == [[24.0, 15.0, 26.0, 35.0]]

    hub.messages.clear()
    asyncio.run(run("no-meta.jsonl"))
    obs = [m for m in hub.messages if m.get("type") == "obstacles"]
    assert obs[-1]["obstacles"] == []  # 前セッションの壁を消す


def test_missing_truth_file_rejected(config, tmp_path, log_file):
    rc = ReplayController(config, FakeHub(), [tmp_path])
    assert asyncio.run(rc.start("ranges-test.jsonl", 0, truth_name="nope.jsonl")) is False


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
