"""パラメータスイープツール (tools/sweep.py) の回帰テスト。実機不要。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import sweep as sw  # noqa: E402

from server.config import load_config  # noqa: E402
from server.simulate import simulate  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent.parent / "server" / "config.yaml"


def make_data(config, duration_s=60.0):
    lines, truth = [], {}
    for msg, t in simulate(config, duration_s, seed=42):
        lines.append(json.dumps(msg))
        truth[(int(t["tag"], 0), t["t_ms"])] = (t["x"], t["y"])
    return lines, truth


def test_apply_override_types(config):
    sw.apply_override(config, "tuning.residual_gate_m", "0.7")
    assert config.tuning.residual_gate_m == 0.7
    sw.apply_override(config, "tuning.max_age_ms", "800")
    assert config.tuning.max_age_ms == 800 and isinstance(config.tuning.max_age_ms, int)


def test_sweep_grid_with_truth(config):
    lines, truth = make_data(config)
    params = {"tuning.residual_gate_m": ["0.5", "5.0"],
              "tuning.sigma_a": ["1.0"]}
    results = sw.sweep(lines, str(CONFIG_PATH), params, truth)
    assert len(results) == 2  # 2 × 1 の直積
    for assignment, m in results:
        assert set(assignment) == set(params)
        assert m["n"] > 300
        assert "cep50" in m and m["cep50"] < 0.30  # 受入基準内
        assert m["trk%"] > 80
    # residual_gate を極端に緩めても標準条件では大きく壊れない (実行できることが主眼)
    ceps = {r[0]["tuning.residual_gate_m"]: r[1]["cep50"] for r in results}
    assert ceps["0.5"] <= ceps["5.0"] + 0.05


def test_sweep_without_truth(config):
    lines, _ = make_data(config, duration_s=30.0)
    results = sw.sweep(lines, str(CONFIG_PATH), {"tuning.gate_margin_m": ["0.6"]}, None)
    (_, m), = results
    assert "cep50" not in m
    assert m["res_mean"] > 0
    assert m["jumps"] == 0
