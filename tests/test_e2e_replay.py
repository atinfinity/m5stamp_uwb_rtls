"""e2e 回帰: シミュレータ → リプレイ → 精度評価 (server-design.md §13)。

受入基準: CEP50 ≤ 0.30 m、TRACKING 中の 1 エポック 2 m 超ジャンプなし。
"""
import json
import math

from server.models import TagTrackState
from server.replay import replay_lines
from server.simulate import SimParams, simulate


def run_sim_and_replay(config, duration_s=120.0, seed=42, params=None):
    truth_map = {}
    lines = []
    for msg, truth in simulate(config, duration_s, seed, params):
        lines.append(json.dumps(msg))
        truth_map[(int(truth["tag"], 0), truth["t_ms"])] = (truth["x"], truth["y"])
    positions = list(replay_lines(lines, config))
    return positions, truth_map


def test_cep50_within_30cm(config):
    positions, truth_map = run_sim_and_replay(config)
    errs = []
    for pos in positions:
        if pos.state is not TagTrackState.TRACKING:
            continue
        t = truth_map.get((pos.tag, pos.t_ms))
        if t is None:
            continue
        errs.append(math.hypot(pos.x_m - t[0], pos.y_m - t[1]))
    assert len(errs) > 500
    errs.sort()
    cep50 = errs[len(errs) // 2]
    cep95 = errs[int(len(errs) * 0.95)]
    print(f"CEP50={cep50:.3f} m CEP95={cep95:.3f} m n={len(errs)}")
    assert cep50 <= 0.30
    assert cep95 <= 1.0


def test_no_track_jumps(config):
    positions, _ = run_sim_and_replay(config)
    last: dict[int, tuple[int, float, float]] = {}
    for pos in positions:
        if pos.state is not TagTrackState.TRACKING:
            continue
        prev = last.get(pos.tag)
        if prev is not None:
            dt_s = (pos.t_ms - prev[0]) / 1000.0
            if 0 < dt_s <= 1.0:
                jump = math.hypot(pos.x_m - prev[1], pos.y_m - prev[2])
                assert jump < 2.0, f"tag {pos.tag}: {jump:.2f} m jump in {dt_s:.1f}s"
        last[pos.tag] = (pos.t_ms, pos.x_m, pos.y_m)


def test_heavy_nlos_still_usable(config):
    """NLoS 20% の劣悪環境でも CEP50 ≤ 0.5 m は維持できること。"""
    params = SimParams(nlos_prob=0.20, dropout_prob=0.10)
    positions, truth_map = run_sim_and_replay(config, duration_s=60, params=params)
    errs = []
    for pos in positions:
        if pos.state is not TagTrackState.TRACKING:
            continue
        t = truth_map.get((pos.tag, pos.t_ms))
        if t:
            errs.append(math.hypot(pos.x_m - t[0], pos.y_m - t[1]))
    assert len(errs) > 100
    errs.sort()
    assert errs[len(errs) // 2] <= 0.5
