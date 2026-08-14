"""合成シミュレータ (server-design.md §13-2)。

歩行モデルの真値軌跡から、ノイズ + 確率的 NLoS バイアス + 欠測を注入した
ranges メッセージ列を生成する。リプレイ・e2e テスト・仮想タグの共通データ源。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterator

from server.config import RtlsConfig, parse_addr


@dataclass
class SimParams:
    rate_hz: float = 2.0
    speed_ms: float = 1.2            # 歩行速度
    sigma_m: float = 0.05            # 測距ガウスノイズ σ
    nlos_prob: float = 0.05          # NLoS バイアス混入率
    nlos_bias_m: tuple[float, float] = (0.3, 2.0)  # 伸びる方向の一様分布
    dropout_prob: float = 0.03       # 欠測率 (ok=false)
    recv_jitter_ms: tuple[int, int] = (5, 40)      # Wi-Fi+ブローカー遅延
    start_t_ms: int = 1_000_000
    margin_m: float = 2.0            # 壁からの距離


@dataclass
class _TagState:
    x: float
    y: float
    wx: float = 0.0
    wy: float = 0.0
    seq: int = 0


def _cell_anchors(config: RtlsConfig, x: float, y: float) -> list[int]:
    """真値座標を含むセル(なければ最近傍セル)のアンカー。"""
    best = None
    best_d = float("inf")
    for cell in config.cells.values():
        x0, y0, x1, y1 = cell.rect
        if x0 <= x <= x1 and y0 <= y <= y1:
            return [parse_addr(a) for a in cell.anchors]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d = (cx - x) ** 2 + (cy - y) ** 2
        if d < best_d:
            best_d, best = d, cell
    assert best is not None
    return [parse_addr(a) for a in best.anchors]


def simulate(
    config: RtlsConfig,
    duration_s: float,
    seed: int = 0,
    params: SimParams | None = None,
) -> Iterator[tuple[dict, dict]]:
    """(ranges メッセージ, 真値) の組をエポック順に生成する。

    ranges メッセージは MQTT ペイロード (server-design.md §4.7) と同形式 +
    recv_ms(サーバー受信時刻の模擬)。
    """
    p = params or SimParams()
    rng = random.Random(seed)
    anchors = config.anchor_by_addr()
    tag_addrs = config.tag_addrs()
    floor = config.floor

    def new_waypoint() -> tuple[float, float]:
        return (
            rng.uniform(p.margin_m, floor.width_m - p.margin_m),
            rng.uniform(p.margin_m, floor.height_m - p.margin_m),
        )

    states: dict[int, _TagState] = {}
    for t in tag_addrs:
        x, y = new_waypoint()
        st = _TagState(x=x, y=y)
        st.wx, st.wy = new_waypoint()
        states[t] = st

    epoch_dt = 1.0 / p.rate_hz
    slot_ms = int(1000.0 / p.rate_hz / max(len(tag_addrs), 1))
    n_epochs = int(duration_s * p.rate_hz)

    for epoch in range(n_epochs):
        for i, tag in enumerate(tag_addrs):
            st = states[tag]
            # 歩行モデル: waypoint へ等速移動、到達したら次の waypoint
            dx, dy = st.wx - st.x, st.wy - st.y
            dist = math.hypot(dx, dy)
            step = p.speed_ms * epoch_dt
            if dist <= step:
                st.x, st.y = st.wx, st.wy
                st.wx, st.wy = new_waypoint()
            else:
                st.x += dx / dist * step
                st.y += dy / dist * step

            t_ms = p.start_t_ms + int(epoch * epoch_dt * 1000) + i * slot_ms
            st.seq += 1

            ranges = []
            for addr in _cell_anchors(config, st.x, st.y):
                a = anchors[addr]
                if rng.random() < p.dropout_prob:
                    ranges.append({"a": f"0x{addr:04X}", "d_mm": 0, "ok": False})
                    continue
                slant = math.sqrt(
                    (a.x - st.x) ** 2 + (a.y - st.y) ** 2
                    + (a.z - floor.tag_height_m) ** 2
                )
                d = slant + rng.gauss(0.0, p.sigma_m)
                if rng.random() < p.nlos_prob:
                    d += rng.uniform(*p.nlos_bias_m)  # NLoS は伸びる方向のみ
                d_mm = int(round(d * 1000)) + a.bias_mm
                ranges.append({"a": f"0x{addr:04X}", "d_mm": d_mm, "ok": True})

            msg = {
                "tag": f"0x{tag:04X}",
                "seq": st.seq,
                "t_ms": t_ms,
                "recv_ms": t_ms + rng.randint(*p.recv_jitter_ms),
                "ranges": ranges,
            }
            truth = {"tag": f"0x{tag:04X}", "t_ms": t_ms,
                     "x": round(st.x, 4), "y": round(st.y, 4)}
            yield msg, truth
