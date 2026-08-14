"""リプレイ (server-design.md §8): ranges JSONL を MQTT を介さず pipeline へ投入する。

使い方:
    python -m server.replay logs/sim_ranges.jsonl --config server/config.yaml \
        --out logs/positions.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from server.cells import CellManager
from server.config import RtlsConfig, load_config
from server.models import Position, RangeSet
from server.positioning.pipeline import TagPipeline


def build_pipelines(config: RtlsConfig) -> dict[int, TagPipeline]:
    cells = CellManager(config)
    return {t: TagPipeline(t, config, cells) for t in config.tag_addrs()}


def replay_lines(lines, config: RtlsConfig):
    """JSONL 行列を処理し Position を順に yield する(テストからも使用)。"""
    pipelines = build_pipelines(config)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        recv_ms = int(d.get("recv_ms", d["t_ms"]))
        rs = RangeSet.from_json(json.dumps(d), recv_ms=recv_ms)
        pl = pipelines.get(rs.tag)
        if pl is None:
            continue
        pos = pl.process(rs)
        if pos is not None:
            yield pos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="ranges JSONL")
    ap.add_argument("--config", default="server/config.yaml")
    ap.add_argument("--out", default=None, help="positions JSONL 出力先 (省略時 stdout)")
    ap.add_argument("--speed", type=float, default=0.0,
                    help="0=最速一括 (既定), 1=実時間再生")
    args = ap.parse_args()

    config = load_config(args.config)
    lines = Path(args.input).read_text().splitlines()

    out = open(args.out, "w") if args.out else sys.stdout
    prev_t: int | None = None
    n = 0
    try:
        for pos in replay_lines(lines, config):
            if args.speed > 0 and prev_t is not None:
                time.sleep(max(0.0, (pos.t_ms - prev_t) / 1000.0 / args.speed))
            prev_t = pos.t_ms
            out.write(pos.to_json() + "\n")
            n += 1
    finally:
        if args.out:
            out.close()
    print(f"replayed {n} positions", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
