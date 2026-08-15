"""C++ ソルバー (rtls_solver) と Python 実装の一致試験 (tag-design.md §10-2)。

シミュレータ出力を両実装のパイプラインへ通し、エポックごとに座標・状態を
突き合わせる。C++ 側は firmware/test_native/parity_main.cpp をビルドして実行。
"""
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from server.config import parse_addr
from server.models import RangeSet
from server.positioning.pipeline import TagPipeline
from server.simulate import simulate

ROOT = Path(__file__).resolve().parent.parent
CXX = shutil.which("c++") or shutil.which("g++")


@pytest.mark.skipif(CXX is None, reason="C++ compiler not available")
def test_cpp_python_parity(config, tmp_path):
    # ---- 入力データ生成 (60 s, 3 タグ) ----
    lines = []
    for msg, _truth in simulate(config, duration_s=60.0, seed=7):
        lines.append(json.dumps(msg))
    ranges_path = tmp_path / "ranges.jsonl"
    ranges_path.write_text("\n".join(lines) + "\n")

    anchors_path = tmp_path / "anchors.txt"
    with anchors_path.open("w") as f:
        f.write(f"tag_height {config.floor.tag_height_m}\n")
        for addr_str, a in config.anchors.items():
            f.write(f"{parse_addr(addr_str):04x} {a.x} {a.y} {a.z} {a.bias_mm}\n")

    # ---- C++ 側: ビルドして実行 ----
    harness = tmp_path / "parity"
    subprocess.run(
        [CXX, "-std=c++17", "-O2", "-I", str(ROOT / "firmware/lib/rtls_solver"),
         "-o", str(harness), str(ROOT / "firmware/test_native/parity_main.cpp")],
        check=True)
    out = subprocess.run([str(harness), str(anchors_path), str(ranges_path)],
                         check=True, capture_output=True, text=True)
    cpp = {}
    for line in out.stdout.splitlines():
        d = json.loads(line)
        cpp[(int(d["tag"], 0), d["t_ms"])] = d

    # ---- Python 側: セル管理なしで同一パイプラインを実行 ----
    pipelines = {t: TagPipeline(t, config, cell_manager=None) for t in config.tag_addrs()}
    py = {}
    for line in lines:
        d = json.loads(line)
        rs = RangeSet.from_json(line, recv_ms=int(d["recv_ms"]))
        pos = pipelines[rs.tag].process(rs)
        if pos is not None:
            py[(pos.tag, pos.t_ms)] = pos

    # ---- 突き合わせ ----
    assert len(py) > 300  # 60 s × 2 Hz × 3 タグ = 360 エポック弱
    # 両実装が出力したエポック集合は一致する (破棄判定・COASTING 判定が同じ)
    assert set(py.keys()) == set(cpp.keys())

    diffs = []
    state_mismatch = 0
    for key, pos in py.items():
        c = cpp[key]
        if pos.state.name != c["state"]:
            state_mismatch += 1
            continue
        if pos.state.name == "TRACKING":
            diffs.append(math.hypot(pos.x_m - c["x_m"], pos.y_m - c["y_m"]))

    assert state_mismatch / len(py) <= 0.01  # 状態一致率 99% 以上
    diffs.sort()
    n = len(diffs)
    assert n > 250
    median = diffs[n // 2]
    p99 = diffs[int(n * 0.99)]
    print(f"parity: n={n} median={median * 1000:.2f} mm "
          f"p99={p99 * 1000:.2f} mm max={diffs[-1] * 1000:.2f} mm "
          f"state_mismatch={state_mismatch}")
    # tag-design.md §10-2: 一致許容 1 cm (中央値)。ソルバーの反復条件差・
    # float/double 差があるため、p99 は 2 cm・最大 10 cm を許容する。
    assert median <= 0.01
    assert p99 <= 0.02
    assert diffs[-1] <= 0.10
