#!/usr/bin/env python3
"""Step 1 計測ログの統計解析。

capture.py が保存した CSV から以下を算出する (ds-twr-design.md §6 の 1./2./5.):
  - 成功率、エラー内訳 (複数アンカー巡回ログではアンカー別にも出す)
  - 距離: 平均・bias(真値との差)・標準偏差 → bias_mm 校正値の元データ
  - 交換所要時間 exchange_us の p50 / p95 / p99 → TDMA スロット設計の根拠
  - サイクル所要時間 cycle_us (複数アンカー巡回時) → アンカー間ギャップの評価

使い方:
    python analyze.py logs/dist5m.csv [logs/dist10m.csv ...]

CSV 形式は 2 種類を受け付ける (FW のヘッダ行で自動判別):
  旧 (1対1):  seq,ok,d_mm,elapsed_ms,exchange_us,err
  新 (巡回):  seq,anchor,ok,d_mm,elapsed_ms,exchange_us,cycle_us,err

依存: 標準ライブラリのみ。
"""
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

LEGACY_COLS = 6
MULTI_COLS = 8


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


@dataclass
class AnchorStats:
    total: int = 0
    d_mm: list[int] = field(default_factory=list)
    ex_us_ok: list[int] = field(default_factory=list)
    errors: Counter = field(default_factory=Counter)

    @property
    def n_ok(self) -> int:
        return len(self.d_mm)


@dataclass
class Stats:
    true_dist_m: float | None = None
    mode: str | None = None
    gap_ms: int | None = None
    anchors: dict[str, AnchorStats] = field(default_factory=dict)
    cycle_us: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(a.total for a in self.anchors.values())

    @property
    def n_ok(self) -> int:
        return sum(a.n_ok for a in self.anchors.values())

    def merged(self) -> AnchorStats:
        m = AnchorStats()
        for a in self.anchors.values():
            m.total += a.total
            m.d_mm += a.d_mm
            m.ex_us_ok += a.ex_us_ok
            m.errors.update(a.errors)
        return m


def _meta_value(line: str, key: str) -> str | None:
    if key not in line:
        return None
    return line.split(key, 1)[1].split()[0]


def parse_csv(text: str) -> Stats:
    st = Stats()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("seq,"):
            continue
        if line.startswith("#"):
            v = _meta_value(line, "true_dist_m=")
            if v is not None:
                st.true_dist_m = float(v)
            v = _meta_value(line, "mode=")
            if v is not None:
                st.mode = v
            v = _meta_value(line, "gap_ms=")
            if v is not None:
                st.gap_ms = int(v)
            continue
        parts = line.split(",")
        if len(parts) == LEGACY_COLS:
            _, ok, dist, _, exchange_us, err = parts
            anchor, cycle_us = "-", "0"
        elif len(parts) == MULTI_COLS:
            _, anchor, ok, dist, _, exchange_us, cycle_us, err = parts
        else:
            continue
        a = st.anchors.setdefault(anchor, AnchorStats())
        a.total += 1
        if ok == "1":
            a.d_mm.append(int(dist))
            a.ex_us_ok.append(int(exchange_us))
        else:
            a.errors[err] += 1
        if int(cycle_us) > 0:
            st.cycle_us.append(int(cycle_us))
    return st


def _print_anchor(a: AnchorStats, true_dist_m: float | None, indent: str) -> None:
    print(f"{indent}試行: {a.total}  成功: {a.n_ok}  成功率: {100.0 * a.n_ok / a.total:.2f}%")
    if a.errors:
        detail = ", ".join(f"{k}×{v}" for k, v in a.errors.most_common())
        print(f"{indent}エラー内訳: {detail}")
    if a.d_mm:
        mean_mm = statistics.fmean(a.d_mm)
        stdev_mm = statistics.stdev(a.d_mm) if a.n_ok > 1 else 0.0
        print(f"{indent}距離: 平均 {mean_mm / 1000:.3f} m  σ {stdev_mm / 10:.1f} cm")
        if true_dist_m is not None:
            bias_mm = mean_mm - true_dist_m * 1000
            print(f"{indent}真値 {true_dist_m:.3f} m → bias {bias_mm / 10:+.1f} cm"
                  f"  (config.yaml の bias_mm 候補: {bias_mm:+.0f})")
    if a.ex_us_ok:
        s = sorted(a.ex_us_ok)
        print(f"{indent}交換時間: p50 {percentile(s, 50) / 1000:.1f} ms"
              f"  p95 {percentile(s, 95) / 1000:.1f} ms"
              f"  p99 {percentile(s, 99) / 1000:.1f} ms"
              f"  max {s[-1] / 1000:.1f} ms")


def analyze(path: Path) -> None:
    st = parse_csv(path.read_text())
    tag = []
    if st.mode:
        tag.append(f"mode={st.mode}-TWR")
    if st.gap_ms is not None:
        tag.append(f"gap_ms={st.gap_ms}")
    print(f"== {path}{' (' + ', '.join(tag) + ')' if tag else ''} ==")
    if st.total == 0:
        print("  データ行がありません")
        return

    multi = len(st.anchors) > 1 or "-" not in st.anchors
    if multi:
        print(f"  アンカー数: {len(st.anchors)}  (全体)")
        _print_anchor(st.merged(), st.true_dist_m, "  ")
        for anchor in sorted(st.anchors):
            print(f"  -- anchor {anchor}")
            _print_anchor(st.anchors[anchor], st.true_dist_m, "     ")
    else:
        _print_anchor(st.anchors["-"], st.true_dist_m, "  ")

    if st.cycle_us:
        s = sorted(st.cycle_us)
        print(f"  サイクル時間 ({len(st.anchors)} アンカー + ギャップ): "
              f"p50 {percentile(s, 50) / 1000:.1f} ms"
              f"  p95 {percentile(s, 95) / 1000:.1f} ms"
              f"  max {s[-1] / 1000:.1f} ms"
              f"  (スロット有効幅 90 ms に対する p95 の余裕: {90 - percentile(s, 95) / 1000:.1f} ms)")
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
