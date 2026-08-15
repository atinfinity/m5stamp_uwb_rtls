#!/usr/bin/env python3
"""TDoA PoC-2: 2 リスナーの RX タイムスタンプからクロック同期品質を評価する。

tdoa-design.md §3.2 の「リファレンスアンカー方式」のオフライン版:
マスターブリンクを 2 台のリスナーで受信したログから、リスナー間の
クロック offset / drift を推定し、補正後の残留誤差 σ を算出する。
σ < 2 ns (≈ 60 cm) が PoC-2 の目標 (§6-2)。1 ns ≈ 30 cm。

使い方:
    uv run python tools/tdoa/sync_analysis.py anchorA.csv anchorB.csv \
        [--master-src 0x00F0] [--tag-src 0x0001]
    uv run python tools/tdoa/sync_analysis.py --selftest

CSV は firmware/tdoa_poc の listener 出力 (src,seq,rx_ticks)。
40 bit タイムスタンプの周回 (~17.2 s) はここでアンラップする。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# DW3xxx デバイス時刻: 1 tick = 1/(128 * 499.2 MHz)
TICK_NS = 1e9 / (128 * 499.2e6)  # ≈ 0.01565 ns
WRAP_TICKS = 1 << 40             # 40 bit (~17.2 s)


def load_listener_csv(path: str | Path, src: int) -> dict[int, float]:
    """指定 src のブリンクを {seq: rx時刻[ns]} で返す (周回アンラップ済み)。"""
    rows: list[tuple[int, int]] = []  # (seq, ticks) 受信順
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("src,"):
            continue
        parts = line.split(",")
        if len(parts) != 3:
            continue
        try:
            row_src = int(parts[0], 0)
            if row_src != src:
                continue
            rows.append((int(parts[1]), int(parts[2])))
        except ValueError:
            continue

    out: dict[int, float] = {}
    offset_ticks = 0
    prev = None
    for seq, ticks in rows:
        if prev is not None and ticks < prev:
            offset_ticks += WRAP_TICKS
        prev = ticks
        out[seq] = (ticks + offset_ticks) * TICK_NS
    return out


def fit_clock(t_a: np.ndarray, t_b: np.ndarray) -> tuple[float, float, float]:
    """B クロックを A 基準でモデル化: tB = offset + (1 + drift) * tA。

    戻り値: (offset_ns, drift, residual_sigma_ns)
    数値安定のため tA を中心化して最小二乗を解く。
    """
    x = t_a - t_a.mean()
    y = (t_b - t_a) - (t_b - t_a).mean()
    slope = float(x @ y / (x @ x))          # drift (無次元)
    resid = y - slope * x
    sigma = float(resid.std(ddof=2)) if len(resid) > 2 else 0.0
    offset = float((t_b - t_a).mean() - slope * t_a.mean())
    return offset, slope, sigma


def corrected_delta(t_a: np.ndarray, t_b: np.ndarray, offset: float,
                    drift: float) -> np.ndarray:
    """同期補正後の到達時刻差 Δt = tB − (offset + (1+drift)·tA) [ns]。"""
    return t_b - (offset + (1.0 + drift) * t_a)


def join(a: dict[int, float], b: dict[int, float]) -> tuple[np.ndarray, np.ndarray]:
    seqs = sorted(set(a) & set(b))
    return (np.array([a[s] for s in seqs]), np.array([b[s] for s in seqs]))


def analyze(path_a: str, path_b: str, master_src: int, tag_src: int | None) -> int:
    ta, tb = join(load_listener_csv(path_a, master_src),
                  load_listener_csv(path_b, master_src))
    if len(ta) < 10:
        print(f"マスターブリンクの共通受信が {len(ta)} 件しかありません (要 10+)")
        return 1
    offset, drift, sigma = fit_clock(ta, tb)
    span_s = (ta[-1] - ta[0]) / 1e9
    print(f"マスターブリンク共通受信: {len(ta)} 件 (観測 {span_s:.1f} s)")
    print(f"  クロック offset: {offset * 1e-6:.3f} ms")
    print(f"  クロック drift : {drift * 1e6:+.3f} ppm")
    print(f"  残留 σ         : {sigma:.3f} ns (≈ {sigma * 30:.1f} cm)")
    verdict = "PASS" if sigma < 2.0 else "FAIL"
    print(f"  PoC-2 判定 (σ < 2 ns): {verdict}")

    if tag_src is not None:
        tta, ttb = join(load_listener_csv(path_a, tag_src),
                        load_listener_csv(path_b, tag_src))
        if len(tta) == 0:
            print(f"タグ (0x{tag_src:04X}) の共通受信がありません")
        else:
            d = corrected_delta(tta, ttb, offset, drift)
            print(f"タグブリンク共通受信: {len(tta)} 件")
            print(f"  補正後 Δt: 平均 {d.mean():.3f} ns  σ {d.std(ddof=1):.3f} ns"
                  f" (≈ {d.std(ddof=1) * 30:.1f} cm)")
    return 0 if sigma < 2.0 else 2


# ---- 自己試験 (実機レス): 合成クロックで推定が復元できることを確認 ----

def make_synthetic(n: int = 300, interval_ns: float = 100e6, offset_ns: float = 1.5e6,
                   drift: float = 3e-6, jitter_ns: float = 0.3,
                   start_ticks: int = 0, seed: int = 0) -> tuple[str, str]:
    """2 リスナー分の CSV 文字列を返す (40bit 周回を含む)。"""
    rng = np.random.default_rng(seed)
    lines_a = ["src,seq,rx_ticks"]
    lines_b = ["src,seq,rx_ticks"]
    for i in range(n):
        t = i * interval_ns
        t_a = t + rng.normal(0, jitter_ns)
        t_b = offset_ns + (1 + drift) * t + rng.normal(0, jitter_ns)
        ticks_a = (start_ticks + int(round(t_a / TICK_NS))) % WRAP_TICKS
        ticks_b = (start_ticks + int(round(t_b / TICK_NS))) % WRAP_TICKS
        lines_a.append(f"0x00F0,{i},{ticks_a}")
        lines_b.append(f"0x00F0,{i},{ticks_b}")
    return "\n".join(lines_a) + "\n", "\n".join(lines_b) + "\n"


def selftest(tmpdir: str | None = None) -> int:
    import tempfile

    tmp = Path(tmpdir or tempfile.mkdtemp())
    # 30 s 観測 → 40bit 周回 (~17.2 s) を必ず跨ぐ開始位置にする
    a, b = make_synthetic(n=300, start_ticks=WRAP_TICKS - int(5e9 / TICK_NS))
    (tmp / "a.csv").write_text(a)
    (tmp / "b.csv").write_text(b)
    ta, tb = join(load_listener_csv(tmp / "a.csv", 0x00F0),
                  load_listener_csv(tmp / "b.csv", 0x00F0))
    offset, drift, sigma = fit_clock(ta, tb)
    # 切片 (offset) は絶対時刻 tA=0 基準のため開始位置に依存する。
    # TDoA に効くのは「補正後 Δt がゼロ中心・低 σ」であること — それで判定する。
    d = corrected_delta(ta, tb, offset, drift)
    ok = (abs(drift * 1e6 - 3.0) < 0.1 and abs(float(d.mean())) < 0.1
          and sigma < 1.0 and len(ta) == 300)
    print(f"selftest: n={len(ta)} drift={drift * 1e6:.3f}ppm sigma={sigma:.3f}ns "
          f"delta_mean={float(d.mean()):.3f}ns -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_a", nargs="?", help="リスナー A の CSV")
    ap.add_argument("csv_b", nargs="?", help="リスナー B の CSV")
    ap.add_argument("--master-src", default="0x00F0")
    ap.add_argument("--tag-src", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.csv_a or not args.csv_b:
        ap.error("csv_a と csv_b を指定 (または --selftest)")
    return analyze(args.csv_a, args.csv_b, int(args.master_src, 0),
                   int(args.tag_src, 0) if args.tag_src else None)


if __name__ == "__main__":
    sys.exit(main())
