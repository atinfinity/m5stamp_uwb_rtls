#!/usr/bin/env python3
"""Step 1 計測: タグ FW の CSV シリアル出力をファイルへ採取する。

使い方:
    python capture.py --port /dev/tty.usbmodem101 --true-dist-m 5.0 \
        --count 1000 --out logs/dist5m.csv

タグ FW (firmware/tag) の出力仕様:
    '#' で始まる行 ... メタデータ/サマリ(そのまま保存)
    それ以外       ... CSV データ行 (seq,ok,d_mm,elapsed_ms,exchange_us,err)

要: pip install pyserial
"""
import argparse
import datetime
import sys
from pathlib import Path

import serial


def main() -> int:
    ap = argparse.ArgumentParser(description="Step1 DS-TWR serial capture")
    ap.add_argument("--port", required=True, help="シリアルポート (例 /dev/tty.usbmodem101)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--true-dist-m", type=float, required=True,
                    help="実測時の真の距離 [m](解析時の bias 計算に使用)")
    ap.add_argument("--count", type=int, default=1000, help="採取するデータ行数")
    ap.add_argument("--out", required=True, help="出力 CSV パス")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with serial.Serial(args.port, args.baud, timeout=5) as ser, out.open("w") as f:
        f.write(f"# capture_time={datetime.datetime.now().isoformat()}\n")
        f.write(f"# true_dist_m={args.true_dist_m}\n")
        n = 0
        header_seen = False
        while n < args.count:
            raw = ser.readline()
            if not raw:
                print("timeout: シリアルから出力がありません", file=sys.stderr)
                continue
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            f.write(line + "\n")
            if line.startswith("#"):
                print(line)
                continue
            if line.startswith("seq,"):
                header_seen = True
                continue
            if not header_seen:
                # 途中から繋いだ場合もデータ行はカウントする
                pass
            n += 1
            if n % 100 == 0:
                print(f"{n}/{args.count}")
    print(f"done: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
