#!/usr/bin/env python3
"""合成シミュレータ CLI — ranges JSONL と真値 JSONL を生成する。

使い方:
    python tools/simulate.py --config server/config.yaml --duration-s 120 \
        --seed 42 --out logs/sim_ranges.jsonl --truth logs/sim_truth.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.config import load_config  # noqa: E402
from server.simulate import SimParams, simulate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="server/config.yaml")
    ap.add_argument("--duration-s", type=float, default=120.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rate-hz", type=float, default=2.0)
    ap.add_argument("--sigma-m", type=float, default=0.05)
    ap.add_argument("--nlos-prob", type=float, default=0.05)
    ap.add_argument("--dropout-prob", type=float, default=0.03)
    ap.add_argument("--out", required=True)
    ap.add_argument("--truth", required=True)
    args = ap.parse_args()

    config = load_config(args.config)
    params = SimParams(rate_hz=args.rate_hz, sigma_m=args.sigma_m,
                       nlos_prob=args.nlos_prob, dropout_prob=args.dropout_prob)

    out = Path(args.out)
    truth_path = Path(args.truth)
    out.parent.mkdir(parents=True, exist_ok=True)
    truth_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with out.open("w") as fo, truth_path.open("w") as ft:
        for msg, truth in simulate(config, args.duration_s, args.seed, params):
            fo.write(json.dumps(msg) + "\n")
            ft.write(json.dumps(truth) + "\n")
            n += 1
    print(f"generated {n} epochs -> {out}, {truth_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
