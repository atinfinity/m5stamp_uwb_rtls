#!/usr/bin/env python3
"""Step 1 計測ログの統計解析。

capture.py が保存した CSV から以下を算出する (ds-twr-design.md §6-1/§6-2):
  - 成功率、エラー内訳
  - 距離: 平均・bias(真値との差)・標準偏差 → bias_mm 校正値の元データ
  - 交換所要時間 exchange_us の p50 / p95 / p99 → TDMA スロット設計の根拠

使い方:
    python analyze.py logs/dist5m.csv [logs/dist10m.csv ...]

依存: 標準ライブラリのみ。
"""
import statistics
import sys
from collections import Counter
from pathlib import Path


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def analyze(path: Path) -> None:
    true_dist_m = None
    mode = None  # DS / SS (FW のヘッダ行 "# tag ... mode=XX" から取得)
    d_mm: list[int] = []
    ex_us_ok: list[int] = []
    errors: Counter[str] = Counter()
    total = 0

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("seq,"):
            continue
        if line.startswith("#"):
            if "true_dist_m=" in line:
                true_dist_m = float(line.split("true_dist_m=")[1].split()[0])
            if "mode=" in line:
                mode = line.split("mode=")[1].split()[0]
            continue
        parts = line.split(",")
        if len(parts) != 6:
            continue
        _, ok, dist, _, exchange_us, err = parts
        total += 1
        if ok == "1":
            d_mm.append(int(dist))
            ex_us_ok.append(int(exchange_us))
        else:
            errors[err] += 1

    print(f"== {path}{f' (mode={mode}-TWR)' if mode else ''} ==")
    if total == 0:
        print("  データ行がありません")
        return

    n_ok = len(d_mm)
    print(f"  試行: {total}  成功: {n_ok}  成功率: {100.0 * n_ok / total:.2f}%")
    if errors:
        detail = ", ".join(f"{k}×{v}" for k, v in errors.most_common())
        print(f"  エラー内訳: {detail}")

    if d_mm:
        mean_mm = statistics.fmean(d_mm)
        stdev_mm = statistics.stdev(d_mm) if n_ok > 1 else 0.0
        print(f"  距離: 平均 {mean_mm / 1000:.3f} m  σ {stdev_mm / 10:.1f} cm")
        if true_dist_m is not None:
            bias_mm = mean_mm - true_dist_m * 1000
            print(f"  真値 {true_dist_m:.3f} m → bias {bias_mm / 10:+.1f} cm"
                  f"  (config.yaml の bias_mm 候補: {bias_mm:+.0f})")

    if ex_us_ok:
        s = sorted(ex_us_ok)
        print(f"  交換時間: p50 {percentile(s, 50) / 1000:.1f} ms"
              f"  p95 {percentile(s, 95) / 1000:.1f} ms"
              f"  p99 {percentile(s, 99) / 1000:.1f} ms"
              f"  max {s[-1] / 1000:.1f} ms")
    print()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    for arg in sys.argv[1:]:
        analyze(Path(arg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
