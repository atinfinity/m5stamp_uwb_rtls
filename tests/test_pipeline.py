import json
import math

from server.cells import CellManager
from server.config import parse_addr
from server.models import RangeSet, TagTrackState
from server.positioning.pipeline import TagPipeline


def make_rangeset(config, tag, seq, t_ms, x, y, nlos_anchor=None, nlos_m=0.0,
                  drop_anchors=(), cell="A"):
    """真値 (x, y) から理想距離の RangeSet を合成する。"""
    anchors = config.anchor_by_addr()
    cell_cfg = config.cells[cell]
    ranges = []
    for a_str in cell_cfg.anchors:
        addr = parse_addr(a_str)
        a = anchors[addr]
        if addr in drop_anchors:
            ranges.append({"a": a_str, "d_mm": 0, "ok": False})
            continue
        slant = math.sqrt((a.x - x) ** 2 + (a.y - y) ** 2
                          + (a.z - config.floor.tag_height_m) ** 2)
        if addr == nlos_anchor:
            slant += nlos_m
        ranges.append({"a": a_str, "d_mm": int(round(slant * 1000)), "ok": True})
    payload = json.dumps({"tag": tag, "seq": seq, "t_ms": t_ms, "ranges": ranges})
    return RangeSet.from_json(payload, recv_ms=t_ms + 20)


def test_tracking_static_tag(config):
    pl = TagPipeline(0x0001, config, CellManager(config))
    pos = None
    for i in range(10):
        rs = make_rangeset(config, 1, seq=i + 1, t_ms=1000 + i * 500, x=10.0, y=8.0)
        pos = pl.process(rs)
    assert pos is not None
    assert pos.state is TagTrackState.TRACKING
    assert math.hypot(pos.x_m - 10.0, pos.y_m - 8.0) < 0.05
    assert pos.cell == "A"


def test_nlos_outlier_removed(config):
    """1 距離に +2 m の NLoS を注入しても leave-one-out で解が復元される。"""
    pl = TagPipeline(0x0001, config, CellManager(config))
    for i in range(5):
        pl.process(make_rangeset(config, 1, i + 1, 1000 + i * 500, 10.0, 8.0))
    pos = pl.process(make_rangeset(config, 1, 6, 4000, 10.0, 8.0,
                                   nlos_anchor=0x0010, nlos_m=2.0))
    assert pos is not None
    assert pos.state is TagTrackState.TRACKING
    assert math.hypot(pos.x_m - 10.0, pos.y_m - 8.0) < 0.30
    assert pos.n_used == 3  # 汚染距離が除外されている


def test_coasting_on_missing_epoch(config):
    pl = TagPipeline(0x0001, config, CellManager(config))
    for i in range(5):
        pl.process(make_rangeset(config, 1, i + 1, 1000 + i * 500, 10.0, 8.0))
    # 4 距離中 2 距離欠測 → 解算不可 → COASTING (予測のみ)
    pos = pl.process(make_rangeset(config, 1, 6, 4000, 10.0, 8.0,
                                   drop_anchors=(0x0010, 0x0011)))
    assert pos is not None
    assert pos.state is TagTrackState.COASTING
    assert pos.n_used == 0
    assert math.hypot(pos.x_m - 10.0, pos.y_m - 8.0) < 0.5


def test_stale_data_rejected(config):
    pl = TagPipeline(0x0001, config, CellManager(config))
    rs = make_rangeset(config, 1, 1, 1000, 10.0, 8.0)
    # recv_ms を大幅に遅らせる → max_age_ms 超過で破棄
    stale = RangeSet(tag=rs.tag, seq=rs.seq, t_ms=rs.t_ms,
                     recv_ms=rs.t_ms + 10_000, ranges=rs.ranges)
    assert pl.process(stale) is None


def test_duplicate_seq_rejected(config):
    pl = TagPipeline(0x0001, config, CellManager(config))
    rs = make_rangeset(config, 1, 5, 1000, 10.0, 8.0)
    assert pl.process(rs) is not None
    assert pl.process(rs) is None  # 同一 seq は破棄


def test_lost_then_reacquire(config):
    pl = TagPipeline(0x0001, config, CellManager(config))
    for i in range(3):
        pl.process(make_rangeset(config, 1, i + 1, 1000 + i * 500, 10.0, 8.0))
    # lost_sec (10 s) を超えて空白 → フィルタ再初期化で別地点でも即追従
    pos = pl.process(make_rangeset(config, 1, 10, 30_000, 20.0, 20.0))
    assert pos is not None
    assert math.hypot(pos.x_m - 20.0, pos.y_m - 20.0) < 0.1
