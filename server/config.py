"""config.yaml の読込と検証 (server-design.md §10)。

起動時検証: セルのアンカー参照・矩形範囲・アドレス重複を検査し、不備は例外で
起動失敗にする。
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


def parse_addr(value: str | int) -> int:
    return int(value, 0) if isinstance(value, str) else int(value)


class MqttConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 1883


class FloorConfig(BaseModel):
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    tag_height_m: float = 1.0


class AnchorConfig(BaseModel):
    x: float
    y: float
    z: float = 2.2
    bias_mm: int = 0


class CellConfig(BaseModel):
    rect: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    anchors: list[str]

    @field_validator("rect")
    @classmethod
    def rect_ordered(cls, v: tuple[float, float, float, float]):
        x0, y0, x1, y1 = v
        if not (x0 < x1 and y0 < y1):
            raise ValueError(f"rect must be (x0,y0,x1,y1) with x0<x1, y0<y1: {v}")
        return v


class TuningConfig(BaseModel):
    max_age_ms: int = 500
    v_max_ms: float = 2.0
    gate_margin_m: float = 0.6
    residual_gate_m: float = 0.5
    sigma_a: float = 1.0
    sigma_m_floor: float = 0.15
    stale_sec: float = 2.0
    lost_sec: float = 10.0
    handover_margin_m: float = 2.0


class RtlsConfig(BaseModel):
    mqtt: MqttConfig = MqttConfig()
    floor: FloorConfig
    anchors: dict[str, AnchorConfig]
    cells: dict[str, CellConfig]
    tags: list[str]
    tuning: TuningConfig = TuningConfig()

    @model_validator(mode="after")
    def validate_consistency(self) -> "RtlsConfig":
        anchor_addrs = {parse_addr(a) for a in self.anchors}
        if len(anchor_addrs) != len(self.anchors):
            raise ValueError("duplicate anchor addresses")
        tag_addrs = {parse_addr(t) for t in self.tags}
        if len(tag_addrs) != len(self.tags):
            raise ValueError("duplicate tag addresses")
        if anchor_addrs & tag_addrs:
            raise ValueError("anchor/tag address overlap")
        for name, cell in self.cells.items():
            for a in cell.anchors:
                if a not in self.anchors:
                    raise ValueError(f"cell {name}: unknown anchor {a}")
            x0, y0, x1, y1 = cell.rect
            if x1 > self.floor.width_m or y1 > self.floor.height_m or x0 < 0 or y0 < 0:
                raise ValueError(f"cell {name}: rect outside floor")
        return self

    # ---- 解算で使いやすい形へのアクセサ ----

    def anchor_by_addr(self) -> dict[int, AnchorConfig]:
        return {parse_addr(k): v for k, v in self.anchors.items()}

    def tag_addrs(self) -> list[int]:
        return [parse_addr(t) for t in self.tags]


def load_config(path: str | Path) -> RtlsConfig:
    data = yaml.safe_load(Path(path).read_text())
    return RtlsConfig.model_validate(data)
