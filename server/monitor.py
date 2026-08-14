"""統計・死活監視 (server-design.md §12)。"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class Monitor:
    def __init__(self, window_s: float = 300.0) -> None:
        self._window_s = window_s
        self.received: dict[int, int] = defaultdict(int)
        self.dropped_invalid: dict[int, int] = defaultdict(int)
        self.dropped_stale: dict[int, int] = defaultdict(int)
        self.clock_skew_ms: dict[int, int] = {}
        # アンカー別の直近測距結果 (ok/ng) — 欠測率算出用
        self._anchor_results: dict[int, deque[tuple[float, bool]]] = defaultdict(deque)

    def on_received(self, tag: int, t_ms: int, recv_ms: int) -> None:
        self.received[tag] += 1
        self.clock_skew_ms[tag] = recv_ms - t_ms

    def on_invalid(self, tag: int) -> None:
        self.dropped_invalid[tag] += 1

    def on_stale(self, tag: int) -> None:
        self.dropped_stale[tag] += 1

    def on_anchor_result(self, anchor: int, ok: bool) -> None:
        dq = self._anchor_results[anchor]
        now = time.monotonic()
        dq.append((now, ok))
        while dq and now - dq[0][0] > self._window_s:
            dq.popleft()

    def anchor_fail_rate(self, anchor: int) -> float | None:
        dq = self._anchor_results.get(anchor)
        if not dq:
            return None
        fails = sum(1 for _, ok in dq if not ok)
        return fails / len(dq)

    def snapshot(self) -> dict:
        anchors = {
            f"0x{a:04X}": {
                "n": len(dq),
                "fail_rate": round(self.anchor_fail_rate(a) or 0.0, 3),
            }
            for a, dq in self._anchor_results.items()
        }
        tags = {
            f"0x{t:04X}": {
                "received": self.received.get(t, 0),
                "dropped_invalid": self.dropped_invalid.get(t, 0),
                "dropped_stale": self.dropped_stale.get(t, 0),
                "clock_skew_ms": self.clock_skew_ms.get(t),
            }
            for t in set(self.received) | set(self.dropped_invalid) | set(self.dropped_stale)
        }
        return {"tags": tags, "anchors": anchors}
