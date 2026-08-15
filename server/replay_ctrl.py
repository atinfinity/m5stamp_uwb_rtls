"""ブラウザ操作のリプレイ再生 (Issue #26 / server-design.md §8 の UI 版)。

recorder が記録した ranges JSONL (またはシミュレータ出力) を読み、
専用のパイプライン群で解算しながら WebSocket ハブへ position を流す。
ライブ運用のパイプラインとは独立しており、サーバーの状態を汚さない
(リプレイ中はライブと画面表示が混ざるため、同時運用は想定しない)。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from server.config import RtlsConfig
from server.models import RangeSet
from server.replay import build_pipelines


class ReplayController:
    def __init__(self, config: RtlsConfig, hub, log_dirs: list[str | Path]) -> None:
        self._config = config
        self._hub = hub
        self._dirs = [Path(d) for d in log_dirs]
        self._task: asyncio.Task | None = None
        self._pause = asyncio.Event()
        self._pause.set()  # set = 再生中
        self.state = "idle"  # idle / playing / paused / finished
        self.file: str | None = None
        self.speed = 1.0
        self.idx = 0
        self.total = 0

    # ---- ログ一覧 / 解決 (パストラバーサル防止のため一覧内のみ許可) ----

    def list_logs(self) -> list[dict]:
        out = []
        for d in self._dirs:
            if not d.is_dir():
                continue
            for p in sorted(d.glob("*.jsonl")):
                out.append({"name": p.name, "dir": str(d),
                            "size": p.stat().st_size,
                            "mtime": int(p.stat().st_mtime)})
        return out

    def _resolve(self, name: str) -> Path | None:
        for entry in self.list_logs():
            if entry["name"] == name:
                return Path(entry["dir"]) / name
        return None

    # ---- 操作 ----

    async def start(self, name: str, speed: float) -> bool:
        path = self._resolve(name)
        if path is None:
            return False
        await self.stop()
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        self.file = name
        self.speed = speed
        self.idx = 0
        self.total = len(lines)
        self.state = "playing"
        self._pause.set()
        self._task = asyncio.create_task(self._run(lines))
        await self._broadcast()
        return True

    def pause(self) -> None:
        if self.state == "playing":
            self.state = "paused"
            self._pause.clear()

    def resume(self) -> None:
        if self.state == "paused":
            self.state = "playing"
            self._pause.set()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.state = "idle"
        self.file = None
        self.idx = 0
        self.total = 0
        await self._broadcast()

    def status(self) -> dict:
        return {"state": self.state, "file": self.file, "speed": self.speed,
                "idx": self.idx, "total": self.total}

    async def _broadcast(self) -> None:
        await self._hub.broadcast({"type": "replay", **self.status()})

    # ---- 再生本体 ----

    async def _run(self, lines: list[str]) -> None:
        pipelines = build_pipelines(self._config)
        prev_t: int | None = None
        for i, line in enumerate(lines):
            await self._pause.wait()
            try:
                d = json.loads(line)
                rs = RangeSet.from_json(line, recv_ms=int(d.get("recv_ms", d["t_ms"])))
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
            pl = pipelines.get(rs.tag)
            if pl is None:
                continue
            if self.speed > 0 and prev_t is not None and rs.t_ms > prev_t:
                await asyncio.sleep(min((rs.t_ms - prev_t) / 1000.0 / self.speed, 2.0))
            elif i % 50 == 0:
                await asyncio.sleep(0)  # 最速再生でもイベントループを塞がない
            prev_t = rs.t_ms
            pos = pl.process(rs)
            self.idx = i + 1
            if pos is not None:
                await self._hub.broadcast(
                    json.loads(pos.to_json()) | {"type": "position", "src": "replay"})
            if (i + 1) % 20 == 0:
                await self._broadcast()
        self.state = "finished"
        await self._broadcast()
