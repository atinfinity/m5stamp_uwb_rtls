# ファームウェア

| 対象 | env | 内容 |
|---|---|---|
| `tag`(本番) | `tag` | アンカー巡回 + TDMA + Wi-Fi/MQTT(Step 2/3、Issue [#6](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/6)) |
| `tag`(計測) | `tag_step1` | 1対1 DS-TWR + CSV 出力(Step 1、Issue [#1](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/1)) |
| `tag`(計測・SS) | `tag_step1_ss` | 1対1 SS-TWR 検証(Issue [#14](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/14)) |
| `anchor` | `anchor` | DS-TWR 応答専用 |
| `anchor`(SS) | `anchor_ss` | SS-TWR 応答(検証用) |

Arduino 非依存ロジック(TDMA スロット判定・MQTT ペイロード生成/解析)は `lib/rtls_common/` にあり、
`./test_native/run.sh` でホスト上の単体テストが実行できる(CI でも実行)。

## 本番モード(env:tag)

Wi-Fi / MQTT / SNTP の接続先は `firmware/tag/platformio.ini` の `build_flags` で指定する
(`WIFI_SSID` / `WIFI_PASS` / `MQTT_HOST`。SNTP は既定で MQTT_HOST の chrony を使用 — 基本設計 §4.9)。

```bash
cd firmware/tag
pio run -e tag -t upload          # 本番モード
pio run -e tag_step1 -t upload    # Step 1 計測モード
```

動作: SNTP 同期後、自スロット(アドレスから決まる 90 ms 窓、スーパーフレーム 500 ms)で
担当アンカー 4 台へ順次 DS-TWR → `rtls/tag/{addr}/ranges` へ publish。
`rtls/tag/{addr}/anchors`(retained)を受信すると担当リストを差し替える(セルハンドオーバー)。

---

# Step 1: DS-TWR 1対1実測

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

# タグ 計測モード (addr 0x0001 → anchor 0x0010 へ 50ms 間隔で測距)
cd ../tag
pio run -e tag_step1 -t upload
```

アドレス・測距間隔は各 `platformio.ini` の `build_flags`(`NODE_ADDR` / `TARGET_ANCHOR` / `RANGE_INTERVAL_MS`)で変更する。

> **注**: board 定義は汎用の `esp32-c5-devkitc-1` を使用している。書き込みに失敗する場合は
> `pio device list` でポートを確認し、`upload_port` を明示すること。

## 計測手順(ds-twr-design.md §6-1, §6-2)

1. 既知距離(レーザー距離計で測定)にタグ・アンカーを設置(高さを揃える)
2. タグのシリアルを capture.py で採取:

```bash
uv run --with pyserial python tools/step1/capture.py --port /dev/tty.usbmodemXXXX \
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

## SS-TWR 検証(Issue #14、ss-twr-design.md §4/§6)

DS-TWR の対照試験として、**同じ設置・同じ距離**で env を SS に替えて同手順を繰り返す:

```bash
cd firmware/anchor && pio run -e anchor_ss -t upload      # アンカーを SS 応答に
cd ../tag && pio run -e tag_step1_ss -t upload            # タグを SS 計測に
# capture.py / analyze.py は共通 (mode は CSV メタデータから自動判別)
python tools/step1/analyze.py logs/ds_dist5m.csv logs/ss_dist5m.csv   # DS/SS を並べて比較
```

判定(3 条件すべて満たしたら SS-TWR を予備方式として有効化):

| # | 条件 | 見方 |
|---|---|---|
| ① | σ ≤ 15 cm・バイアス ≤ 10 cm | **CFO 補償の有無がここで判明**。補償なしなら m 級誤差が出て即不成立(ss-twr-design.md §2.2) |
| ② | 交換時間が DS 比 30% 以上短い | analyze.py の p50 を比較 |
| ③ | リプレイで CEP50 ≤ 30 cm 維持 | Step 2 以降のログで確認 |

- bias は方式ごとに異なりうるため、**DS/SS 別々に校正値を記録**する
- 温度依存(始動直後 vs 30 分後)も §6-1 に従い両方式で採取する
- 不成立の場合は実測値を ss-twr-design.md に追記して Issue #14 を close

## タグ CSV 出力仕様

```
seq,ok,d_mm,elapsed_ms,exchange_us,err
```

- `exchange_us`: `requestDSRange()` 呼出し全体の実測時間(ホスト SPI 処理込み)。スロット設計はこちらを使う
- `elapsed_ms`: ライブラリが報告する所要時間
- `#` で始まる行はメタデータ/サマリ
