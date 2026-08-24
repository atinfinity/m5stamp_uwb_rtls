"""tools/step1/analyze.py の CSV パーサ (旧 1対1 形式 / 新 巡回形式) の回帰テスト。"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("step1_analyze", ROOT / "tools/step1/analyze.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["step1_analyze"] = mod
    spec.loader.exec_module(mod)
    return mod


LEGACY = """# capture_time=2026-08-25T00:00:00
# true_dist_m=5.0
# tag addr=0x0001 anchor=0x0010 interval_ms=50 mode=DS chip=QM33120
seq,ok,d_mm,elapsed_ms,exchange_us,err
1,1,5010,6,6500,-
2,1,4990,6,6700,-
3,0,0,100,100200,RxTimeout
"""

MULTI = """# capture_time=2026-08-25T00:00:00
# true_dist_m=5.0
# tag addr=0x0001 anchors=0x0010,0x0011 gap_ms=2 interval_ms=200 mode=DS chip=QM33120
seq,anchor,ok,d_mm,elapsed_ms,exchange_us,cycle_us,err
1,0x0010,1,5010,6,6500,0,-
1,0x0011,1,5100,6,6600,15200,-
2,0x0010,0,0,100,100200,0,RangeFrameMismatch
2,0x0011,1,5080,6,6700,109000,-
"""


def test_parse_legacy_format():
    m = _load()
    st = m.parse_csv(LEGACY)
    assert st.mode == "DS" and st.true_dist_m == 5.0 and st.gap_ms is None
    assert list(st.anchors) == ["-"]
    a = st.anchors["-"]
    assert a.total == 3 and a.n_ok == 2
    assert a.errors == {"RxTimeout": 1}
    assert st.cycle_us == []


def test_parse_multi_anchor_format():
    m = _load()
    st = m.parse_csv(MULTI)
    assert st.gap_ms == 2
    assert sorted(st.anchors) == ["0x0010", "0x0011"]
    assert st.anchors["0x0010"].n_ok == 1 and st.anchors["0x0010"].total == 2
    assert st.anchors["0x0010"].errors == {"RangeFrameMismatch": 1}
    assert st.anchors["0x0011"].n_ok == 2
    # cycle_us はサイクル最後の行にだけ入る (0 は無視)
    assert st.cycle_us == [15200, 109000]
    merged = st.merged()
    assert merged.total == 4 and merged.n_ok == 3


def test_unknown_column_count_is_skipped():
    m = _load()
    st = m.parse_csv("seq,ok\n1,1\n1,2,3,4,5,6,7\n")
    assert st.total == 0
