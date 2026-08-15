"""データ型定義 (server-design.md §4)。

pipeline は MQTT を知らない: 入出力はこのモジュールの型のみ。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum, auto


class TagTrackState(Enum):
    INIT = auto()      # フィルタ未初期化
    TRACKING = auto()  # 通常追尾
    COASTING = auto()  # 当該エポック欠測、予測のみで出力
    STALE = auto()     # stale_sec 以上更新なし(UI 警告)
    LOST = auto()      # lost_sec 以上更新なし(UI 非表示)


@dataclass(frozen=True)
class Range:
    anchor: int  # ショートアドレス (例 0x0010)
    d_mm: int    # 斜距離。ok=False のとき無効
    ok: bool


@dataclass(frozen=True)
class RangeSet:
    """rtls/tag/{id}/ranges 1 件に対応。"""

    tag: int
    seq: int
    t_ms: int     # タグ側タイムスタンプ (SNTP 同期済み)
    recv_ms: int  # サーバー受信時刻
    ranges: tuple[Range, ...]

    @staticmethod
    def from_json(payload: str | bytes, recv_ms: int) -> "RangeSet":
        d = json.loads(payload)
        return RangeSet(
            tag=int(d["tag"], 0) if isinstance(d["tag"], str) else int(d["tag"]),
            seq=int(d["seq"]),
            t_ms=int(d["t_ms"]),
            recv_ms=recv_ms,
            ranges=tuple(
                Range(
                    anchor=int(r["a"], 0) if isinstance(r["a"], str) else int(r["a"]),
                    d_mm=int(r["d_mm"]),
                    ok=bool(r["ok"]),
                )
                for r in d["ranges"]
            ),
        )


@dataclass(frozen=True)
class Position:
    """rtls/tag/{id}/position 1 件に対応。"""

    tag: int
    t_ms: int
    x_m: float
    y_m: float
    vx_ms: float
    vy_ms: float
    n_used: int        # 解算に使った距離数 (COASTING 時 0)
    residual_m: float  # 使用距離の RMS 残差
    cell: str
    state: TagTrackState
    used: tuple[int, ...] = ()      # 解算に使ったアンカー
    rejected: tuple[int, ...] = ()  # ゲート/外れ値除去で棄却したアンカー

    def to_json(self) -> str:
        return json.dumps(
            {
                "tag": f"0x{self.tag:04X}",
                "t_ms": self.t_ms,
                "x_m": round(self.x_m, 3),
                "y_m": round(self.y_m, 3),
                "vx_ms": round(self.vx_ms, 3),
                "vy_ms": round(self.vy_ms, 3),
                "quality": {"n_anchors": self.n_used, "residual_m": round(self.residual_m, 3)},
                "anchors_used": [f"0x{a:04X}" for a in self.used],
                "anchors_rejected": [f"0x{a:04X}" for a in self.rejected],
                "cell": self.cell,
                "state": self.state.name,
            }
        )
