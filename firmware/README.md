# ファームウェア(Step 1: DS-TWR 1対1実測)

Issue [#1](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/1) / 設計: [ds-twr-design.md](../docs/ds-twr-design.md) §6

## ハードウェア準備

- M5Stamp C5 + Stamp UWB F を **2 セット**。各セットは付属の 0.5mm-12P FPC ケーブルで直結(ピン割当は自動で `rtls_common.h` と一致)
- 両ノード USB-C で PC へ接続(タグ側は計測ログの採取にシリアルを使う)
- アンテナ端が金属・机面に近づかないよう治具等で浮かせる(基本設計 §3.3)

## ビルドと書き込み

ESP32-C5 の Arduino サポートは pioarduino 版 platform を使用(platformio.ini 設定済み)。

```bash
# アンカー (addr 0x0010)
cd firmware/anchor
pio run -t upload

# タグ (addr 0x0001 → anchor 0x0010 へ 50ms 間隔で測距)
cd ../tag
pio run -t upload
```

アドレス・測距間隔は各 `platformio.ini` の `build_flags`(`NODE_ADDR` / `TARGET_ANCHOR` / `RANGE_INTERVAL_MS`)で変更する。

> **注**: board 定義は汎用の `esp32-c5-devkitc-1` を使用している。書き込みに失敗する場合は
> `pio device list` でポートを確認し、`upload_port` を明示すること。

## 計測手順(ds-twr-design.md §6-1, §6-2)

1. 既知距離(レーザー距離計で測定)にタグ・アンカーを設置(高さを揃える)
2. タグのシリアルを capture.py で採取:

```bash
pip install pyserial
python tools/step1/capture.py --port /dev/tty.usbmodemXXXX \
    --true-dist-m 5.000 --count 1000 --out logs/dist5m.csv
```

3. 距離を変えて繰り返し(1 / 5 / 10 / 20 / 40 m)
4. 解析:

```bash
python tools/step1/analyze.py logs/dist*.csv
```

出力(成功率、bias、σ、交換時間 p50/p95/p99)を Issue #1 に記録し、以下を更新する:

- `bias_mm` 校正値 → server 設計 §10 の config.yaml へ
- 交換時間 p95 → 基本設計 §4.4 の TDMA スロット幅
- `rtls_common.h` のタイミング定数(`responseTxDelayUus` を 3000→1500 µs に詰める実験は
  `kDsResponseTxDelayUus` を変更して同手順で比較)

## タグ CSV 出力仕様

```
seq,ok,d_mm,elapsed_ms,exchange_us,err
```

- `exchange_us`: `requestDSRange()` 呼出し全体の実測時間(ホスト SPI 処理込み)。スロット設計はこちらを使う
- `elapsed_ms`: ライブラリが報告する所要時間
- `#` で始まる行はメタデータ/サマリ
