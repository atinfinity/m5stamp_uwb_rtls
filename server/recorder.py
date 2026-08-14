"""生距離の JSONL 記録 (server-design.md §8)。

受信ペイロードを検証前の生のまま日次ファイルへ追記する。リプレイの入力になる。
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path


class JsonlRecorder:
    def __init__(self, log_dir: str | Path = "logs") -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self) -> Path:
        day = datetime.date.today().strftime("%Y%m%d")
        return self._dir / f"ranges-{day}.jsonl"

    def append(self, payload: str | bytes, recv_ms: int) -> None:
        if isinstance(payload, bytes):
            payload = payload.decode(errors="replace")
        try:
            d = json.loads(payload)
            d["recv_ms"] = recv_ms
            line = json.dumps(d)
        except json.JSONDecodeError:
            line = json.dumps({"recv_ms": recv_ms, "raw": payload})
        with self._path().open("a") as f:
            f.write(line + "\n")
