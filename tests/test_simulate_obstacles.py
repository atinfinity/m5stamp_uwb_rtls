"""空間 NLoS モデル (遮蔽物矩形) のテスト (Issue #21)。実機不要。"""
import json
import math

from server.models import TagTrackState
from server.replay import replay_lines
from server.simulate import SimParams, is_blocked, segment_intersects_rect, simulate

RECT = (10.0, 10.0, 20.0, 20.0)


def test_segment_rect_intersection():
    # 横断
    assert segment_intersects_rect((0, 15), (30, 15), RECT)
    # 斜め横断
    assert segment_intersects_rect((5, 5), (25, 25), RECT)
    # 端点が矩形内
    assert segment_intersects_rect((15, 15), (40, 40), RECT)
    # 完全に外 (平行)
    assert not segment_intersects_rect((0, 5), (30, 5), RECT)
    # 角をかすめない対角
    assert not segment_intersects_rect((0, 25), (5, 30), RECT)
    # 両端点が同じ側
    assert not segment_intersects_rect((25, 0), (30, 5), RECT)


def test_is_blocked_multiple_obstacles():
    p = SimParams(obstacles=((0, 0, 1, 1), RECT))
    assert is_blocked(p, (5, 15), (25, 15))       # RECT に遮られる
    assert not is_blocked(p, (5, 25), (5, 40))    # どちらにも遮られない


def test_blocked_paths_get_persistent_bias(config):
    """遮蔽された測距は真値より系統的に長く、見通しはゼロ中心になる。"""
    params = SimParams(nlos_prob=0.0, dropout_prob=0.0, obstacle_dropout_prob=0.0,
                       obstacles=((15.0, 0.0, 20.0, 50.0),))  # フロアを縦断する壁
    anchors = config.anchor_by_addr()
    blocked_errs, clear_errs = [], []
    for msg, truth in simulate(config, duration_s=60.0, seed=1, params=params):
        tx, ty = truth["x"], truth["y"]
        for r in msg["ranges"]:
            if not r["ok"]:
                continue
            a = anchors[int(r["a"], 0)]
            slant = math.sqrt((a.x - tx) ** 2 + (a.y - ty) ** 2
                              + (a.z - config.floor.tag_height_m) ** 2)
            err = r["d_mm"] / 1000.0 - slant
            if is_blocked(params, (tx, ty), (a.x, a.y)):
                blocked_errs.append(err)
            else:
                clear_errs.append(err)
    assert len(blocked_errs) > 50 and len(clear_errs) > 50
    assert sum(blocked_errs) / len(blocked_errs) > 0.3   # 遮蔽 → 常時伸びる
    assert abs(sum(clear_errs) / len(clear_errs)) < 0.02  # 見通し → ゼロ中心


def test_pipeline_survives_wall(config):
    """壁 1 枚程度なら外れ値除去が効き、CEP50 ≤ 0.5 m を維持できる。"""
    params = SimParams(obstacles=((24.0, 20.0, 26.0, 30.0),))  # 中央に小さな壁
    truth_map, lines = {}, []
    for msg, truth in simulate(config, duration_s=120.0, seed=4, params=params):
        lines.append(json.dumps(msg))
        truth_map[(int(truth["tag"], 0), truth["t_ms"])] = (truth["x"], truth["y"])
    errs = []
    for pos in replay_lines(lines, config):
        if pos.state is not TagTrackState.TRACKING:
            continue
        t = truth_map.get((pos.tag, pos.t_ms))
        if t:
            errs.append(math.hypot(pos.x_m - t[0], pos.y_m - t[1]))
    assert len(errs) > 300
    errs.sort()
    assert errs[len(errs) // 2] <= 0.5
