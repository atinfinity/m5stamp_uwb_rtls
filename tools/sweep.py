#!/usr/bin/env python3
"""パラメータスイープ: tuning のグリッドをリプレイ一括評価する (Issue #20)。

同一の ranges JSONL に対して tuning パラメータの全組合せをリプレイし、
評価表を出力する。algorithm-guide.md §2 の開発ループの自動化。

使い方:
    # 真値あり (シミュレータ出力): CEP で評価
    uv run python tools/sweep.py logs/sim_ranges.jsonl --truth logs/sim_truth.jsonl \
        --param tuning.residual_gate_m=0.3,0.5,0.7 \
        --param tuning.sigma_a=0.5,1.0,2.0

    # 真値なし (実測ログ): 残差・TRACKING率・ジャンプ数で評価
    uv run python tools/sweep.py logs/ranges-20260901.jsonl \
        --param tuning.gate_margin_m=0.4,0.6,0.8

--param は `属性パス=候補1,候補2,...` 形式で繰り返し指定できる (直積を評価)。
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.config import RtlsConfig, load_config  # noqa: E402
from server.models import TagTrackState  # noqa: E402
from server.replay import replay_lines  # noqa: E402


def apply_override(config: RtlsConfig, path: str, raw: str) -> None:
    """`tuning.residual_gate_m` のような属性パスへ値を設定する (型は既存値に合わせる)。"""
    obj = config
    parts = path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    current = getattr(obj, parts[-1])
    setattr(obj, parts[-1], type(current)(raw))


def load_truth(path: str | Path) -> dict[tuple[int, int], tuple[float, float]]:
    truth = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        truth[(int(d["tag"], 0), d["t_ms"])] = (d["x"], d["y"])
    return truth


def evaluate(lines: list[str], config: RtlsConfig,
             truth: dict | None) -> dict[str, float]:
    """1 コンフィグぶんのリプレイと指標算出。"""
    n_total = 0
    n_tracking = 0
    residuals: list[float] = []
    errs: list[float] = []
    jumps = 0
    last: dict[int, tuple[int, float, float]] = {}

    for pos in replay_lines(lines, config):
        n_total += 1
        if pos.state is not TagTrackState.TRACKING:
            continue
        n_tracking += 1
        residuals.append(pos.residual_m)
        prev = last.get(pos.tag)
        if prev is not None and 0 < (pos.t_ms - prev[0]) <= 1000:
            if math.hypot(pos.x_m - prev[1], pos.y_m - prev[2]) > 2.0:
                jumps += 1
        last[pos.tag] = (pos.t_ms, pos.x_m, pos.y_m)
        if truth is not None:
            t = truth.get((pos.tag, pos.t_ms))
            if t is not None:
                errs.append(math.hypot(pos.x_m - t[0], pos.y_m - t[1]))

    out: dict[str, float] = {
        "n": n_total,
        "trk%": 100.0 * n_tracking / n_total if n_total else 0.0,
        "res_mean": sum(residuals) / len(residuals) if residuals else float("nan"),
        "jumps": jumps,
    }
    if truth is not None and errs:
        errs.sort()
        out["cep50"] = errs[len(errs) // 2]
        out["cep95"] = errs[int(len(errs) * 0.95)]
        out["max"] = errs[-1]
    return out


def sweep(lines: list[str], config_path: str, params: dict[str, list[str]],
          truth: dict | None) -> list[tuple[dict[str, str], dict[str, float]]]:
    """全組合せを評価して (組合せ, 指標) のリストを返す。"""
    results = []
    keys = list(params.keys())
    for combo in itertools.product(*(params[k] for k in keys)):
        config = load_config(config_path)
        assignment = dict(zip(keys, combo))
        for path, raw in assignment.items():
            apply_override(config, path, raw)
        results.append((assignment, evaluate(lines, config, truth)))
    return results


def print_table(results, params: dict[str, list[str]], has_truth: bool) -> None:
    keys = list(params.keys())
    short = [k.split(".")[-1] for k in keys]
    metric_cols = (["cep50", "cep95", "max"] if has_truth else []) + \
        ["trk%", "res_mean", "jumps"]
    header = short + metric_cols
    # 並び順: 真値ありは cep50、なしは res_mean
    sort_key = "cep50" if has_truth else "res_mean"
    rows = sorted(results, key=lambda r: r[1].get(sort_key, float("inf")))

    widths = [max(len(h), 8) for h in header]
    print("  ".join(h.rjust(w) for h, w in zip(header, widths)))
    for assignment, m in rows:
        cells = [assignment[k] for k in keys]
        for col in metric_cols:
            v = m.get(col)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                cells.append("-")
            elif col in ("jumps", "n"):
                cells.append(str(int(v)))
            elif col == "trk%":
                cells.append(f"{v:.1f}")
            else:
                cells.append(f"{v:.3f}")
        print("  ".join(c.rjust(w) for c, w in zip(cells, widths)))
    best = rows[0][0]
    print(f"\nbest ({sort_key}): " + ", ".join(f"{k}={v}" for k, v in best.items()))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ranges", help="ranges JSONL (シミュレータ出力 or recorder ログ)")
    ap.add_argument("--config", default="server/config.yaml")
    ap.add_argument("--truth", default=None, help="真値 JSONL (あれば CEP を算出)")
    ap.add_argument("--param", action="append", default=[],
                    metavar="PATH=V1,V2,...",
                    help="スイープする属性パスと候補値 (繰り返し可)")
    args = ap.parse_args()
    if not args.param:
        ap.error("--param を 1 つ以上指定してください")

    params: dict[str, list[str]] = {}
    for spec in args.param:
        path, _, values = spec.partition("=")
        if not values:
            ap.error(f"--param の形式が不正: {spec}")
        params[path] = values.split(",")

    lines = Path(args.ranges).read_text().splitlines()
    truth = load_truth(args.truth) if args.truth else None
    n_combo = math.prod(len(v) for v in params.values())
    print(f"{n_combo} 組合せ × {len(lines)} エポックを評価中…")
    results = sweep(lines, args.config, params, truth)
    print_table(results, params, has_truth=truth is not None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
