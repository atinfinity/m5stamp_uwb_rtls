"""セル判定・ハンドオーバー (server-design.md §6)。

ヒステリシス: 現セルの矩形を handover_margin_m 外側に拡張した領域を出るまで
現セルを維持し、境界での配信フラッピングを防ぐ。
"""
from __future__ import annotations

from server.config import RtlsConfig, parse_addr


class CellManager:
    def __init__(self, config: RtlsConfig) -> None:
        self._cells = config.cells
        self._margin = config.tuning.handover_margin_m
        # LOST タグ再捕捉用: フロア中心に最も近いセルのアンカーリスト
        cx = config.floor.width_m / 2
        cy = config.floor.height_m / 2
        center_cell = min(
            self._cells.items(),
            key=lambda kv: (self._rect_center(kv[1].rect)[0] - cx) ** 2
            + (self._rect_center(kv[1].rect)[1] - cy) ** 2,
        )[0]
        self._acquisition_cell = center_cell

    @staticmethod
    def _rect_center(rect: tuple[float, float, float, float]) -> tuple[float, float]:
        x0, y0, x1, y1 = rect
        return (x0 + x1) / 2, (y0 + y1) / 2

    @staticmethod
    def _contains(rect: tuple[float, float, float, float], x: float, y: float,
                  margin: float = 0.0) -> bool:
        x0, y0, x1, y1 = rect
        return (x0 - margin) <= x <= (x1 + margin) and (y0 - margin) <= y <= (y1 + margin)

    def acquisition_cell(self) -> str:
        return self._acquisition_cell

    def anchors_of(self, cell: str) -> list[int]:
        return [parse_addr(a) for a in self._cells[cell].anchors]

    def select(self, x: float, y: float, current: str | None) -> str:
        """座標からセルを決める。current があればヒステリシス付き。"""
        if current is not None and current in self._cells:
            if self._contains(self._cells[current].rect, x, y, self._margin):
                return current
        # 現セル圏外(または初回): 座標を含むセル、なければ最近傍セル
        for name, cell in self._cells.items():
            if self._contains(cell.rect, x, y):
                return name
        return min(
            self._cells.items(),
            key=lambda kv: (self._rect_center(kv[1].rect)[0] - x) ** 2
            + (self._rect_center(kv[1].rect)[1] - y) ** 2,
        )[0]
