"""TDoA PoC 解析ツール (tools/tdoa/sync_analysis.py) の回帰テスト。実機不要。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "tdoa"))

import sync_analysis as sa  # noqa: E402


def test_selftest_passes(tmp_path):
    assert sa.selftest(str(tmp_path)) == 0


def test_fit_recovers_clock_model(tmp_path):
    a, b = sa.make_synthetic(n=200, offset_ns=2.0e6, drift=-5e-6, jitter_ns=0.2, seed=3)
    (tmp_path / "a.csv").write_text(a)
    (tmp_path / "b.csv").write_text(b)
    ta, tb = sa.join(sa.load_listener_csv(tmp_path / "a.csv", 0x00F0),
                     sa.load_listener_csv(tmp_path / "b.csv", 0x00F0))
    offset, drift, sigma = sa.fit_clock(ta, tb)
    assert abs(drift * 1e6 - (-5.0)) < 0.1     # drift [ppm] を復元
    assert abs(offset - 2.0e6) < 100           # offset [ns] を復元
    assert sigma < 2 * 0.2 * 1.5               # 残留 σ ≈ √2×jitter 程度

    # 補正後 Δt はゼロ中心・ジッタ程度に収まる
    d = sa.corrected_delta(ta, tb, offset, drift)
    assert abs(d.mean()) < 0.1
    assert d.std() < 0.5


def test_wrap_unwrapping(tmp_path):
    """40bit 周回を跨いでも時刻が単調増加としてアンラップされる。"""
    start = sa.WRAP_TICKS - int(2e9 / sa.TICK_NS)  # 周回 2 秒前から開始
    a, _ = sa.make_synthetic(n=100, start_ticks=start, jitter_ns=0.0)
    (tmp_path / "a.csv").write_text(a)
    t = sa.load_listener_csv(tmp_path / "a.csv", 0x00F0)
    times = [t[s] for s in sorted(t)]
    diffs = np.diff(times)
    assert len(times) == 100
    assert np.all(diffs > 0)                       # 単調増加
    assert np.allclose(diffs, 100e6, atol=1.0)     # 100 ms 間隔が保存される


def test_missing_and_foreign_rows_ignored(tmp_path):
    csv = ("# comment\nsrc,seq,rx_ticks\n"
           "0x00F0,1,1000\n0x0001,1,999\nbroken,line\n0x00F0,2,2000\n")
    (tmp_path / "a.csv").write_text(csv)
    t = sa.load_listener_csv(tmp_path / "a.csv", 0x00F0)
    assert set(t.keys()) == {1, 2}


def test_interp_tolerates_drift_wander(tmp_path):
    """drift が観測中に動いても、内挿誤差はジッタ程度に収まる (全体直線近似は破綻する)。"""
    # 120 s で drift が 0.48 ppm 動く (PoC-2 実測と同程度)
    a, b = sa.make_synthetic(n=1200, drift=3.2e-6, drift_rate=4e-9, jitter_ns=0.3, seed=5)
    (tmp_path / "a.csv").write_text(a)
    (tmp_path / "b.csv").write_text(b)
    ta, tb = sa.join(sa.load_listener_csv(tmp_path / "a.csv", 0x00F0),
                     sa.load_listener_csv(tmp_path / "b.csv", 0x00F0))
    _, _, sigma_fit = sa.fit_clock(ta, tb)
    e = sa.interp_residual(ta, tb)
    assert sigma_fit > 100                    # 1 本の直線では µs 級に崩れる
    assert len(e) == len(ta) - 2
    assert e.std() < 0.3 * np.sqrt(2 * 1.5) * 1.2  # √1.5 × (1 組の雑音 √2·jitter)


def test_interp_delta_recovers_tag_tdoa(tmp_path):
    """タグブリンクの到達時刻差を、前後のマスターブリンクで補正して復元できる。"""
    a, b = sa.make_synthetic(n=300, drift=3e-6, drift_rate=4e-9, jitter_ns=0.0, seed=1)
    (tmp_path / "a.csv").write_text(a)
    (tmp_path / "b.csv").write_text(b)
    ta, tb = sa.join(sa.load_listener_csv(tmp_path / "a.csv", 0x00F0),
                     sa.load_listener_csv(tmp_path / "b.csv", 0x00F0))
    # マスターブリンクの中間 (50 ms 後) に、真の到達時刻差 +5 ns のタグブリンクを置く
    tag_a = ta[:-1] + 50e6
    master_b = np.interp(tag_a, ta, tb - ta) + tag_a
    tag_b = master_b + 5.0
    d = sa.interp_delta(tag_a, tag_b, ta, tb)
    assert np.allclose(d, 5.0, atol=0.2)
