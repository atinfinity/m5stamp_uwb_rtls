# ファームウェア

| 対象 | env | 内容 |
|---|---|---|
| `tag`(本番) | `tag` | アンカー巡回 + TDMA + Wi-Fi/MQTT(Step 2/3、Issue [#6](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/6)) |
| `tag`(計測) | `tag_step1` | 1対1 DS-TWR + CSV 出力(Step 1、Issue [#1](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/1)) |
| `tag`(計測・SS) | `tag_step1_ss` | 1対1 SS-TWR 検証(Issue [#14](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/14)) |
| `anchor` | `anchor` | DS-TWR 応答専用 |
| `anchor`(SS) | `anchor_ss` | SS-TWR 応答(検証用) |
| `tdoa_poc` | `blink_tx` / `listener` | TDoA PoC: 周期ブリンク送信 / RX タイムスタンプ計測(Issue [#16](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/16)) |

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

- M5Stamp C5 + Stamp UWB F を **2 セット**。各セットは付属の 0.5mm-12P FPC ケーブルで直結(ピン割当は自動で `rtls_common.h` と一致)。組み立ての詳細は [docs/hardware.md](../docs/hardware.md) を参照
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

## 計測手順(ds-twr-design.md §6 の 1. と 2.)

1. 既知距離(レーザー距離計で測定)にタグ・アンカーを設置(高さを揃える)
2. タグのシリアルを capture.py で採取:

```bash
uv run --with pyserial python tools/step1/capture.py --port /dev/tty.usbmodemXXXX \
    --true-dist-m 5.000 --count 1000 --out logs/dist5m.csv
```

3. 距離を変えて繰り返し(1 / 5 / 10 / 20 / 40 m)
4. 解析:

```bash
uv run python tools/step1/analyze.py logs/dist*.csv
```

出力(成功率、bias、σ、交換時間 p50/p95/p99)を Issue #1 に記録し、以下を更新する:

- `bias_mm` 校正値 → server 設計 §10 の config.yaml へ
- 交換時間 p95 → 基本設計 §4.4 の TDMA スロット幅
- `rtls_common.h` のタイミング定数 — アンカーの応答遅延はライブラリ設定 `responseTxDelayUus` に
  代入される定数 `kDsResponseTxDelayUus` で決まる。3000→1500 µs に詰める実験は、この定数を
  変更して同手順で比較する

## SS-TWR 検証(Issue #14、ss-twr-design.md §4/§6)

DS-TWR の対照試験として、**同じ設置・同じ距離**で env を SS に替えて同手順を繰り返す:

```bash
cd firmware/anchor && pio run -e anchor_ss -t upload      # アンカーを SS 応答に
cd ../tag && pio run -e tag_step1_ss -t upload            # タグを SS 計測に
# capture.py / analyze.py は共通 (mode は CSV メタデータから自動判別)
uv run python tools/step1/analyze.py logs/ds_dist5m.csv logs/ss_dist5m.csv   # DS/SS を並べて比較
```

判定(3 条件すべて満たしたら SS-TWR を予備方式として有効化):

| # | 条件 | 見方 |
|---|---|---|
| ① | σ ≤ 15 cm・バイアス ≤ 10 cm | **CFO 補償の有無がここで判明**。補償なしなら m 級誤差が出て即不成立(ss-twr-design.md §2.2) |
| ② | 交換時間が DS 比 30% 以上短い | analyze.py の p50 を比較 |
| ③ | リプレイで CEP50 ≤ 30 cm 維持 | Step 2 以降のログで確認 |

- bias は方式ごとに異なりうるため、**DS/SS 別々に校正値を記録**する
- 温度依存(始動直後 vs 30 分後)も ss-twr-design.md §6 の 1. に従い両方式で採取する
- 不成立の場合は実測値を ss-twr-design.md に追記して Issue #14 を close

## TDoA PoC(Issue #16、tdoa-design.md §6)

将来方式 TDoA のゲート条件を検証する。公開 API に RX タイムスタンプが無いため、
listener FW は同梱 `qm33120w_sdk` の `dwt_readrxtimestamp()` を直叩きする
(40 bit、1 tick ≈ 15.65 ps、~17.2 s で周回)。

**PoC-1(2 ノード): タイムスタンプ取得可否**

```bash
cd firmware/tdoa_poc
pio run -e blink_tx -t upload    # ノード1: 100ms 毎にブリンク送信 (addr 0x00F0)
pio run -e listener -t upload    # ノード2: 受信 + "src,seq,rx_ticks" を CSV 出力
```

判定: listener の `rx_ticks` がブリンクごとに**単調増加**していれば取得成功
(増加しない/常に同値なら `receiveFrame()` 実装がレジスタを上書きしており、ライブラリ改造が必要)。

**PoC-2(3 ノード): 2 アンカー無線同期**

blink_tx 1 台 + listener 2 台(それぞれ PC にシリアル接続し CSV を採取)で:

```bash
uv run python tools/tdoa/sync_analysis.py anchorA.csv anchorB.csv
# → クロック offset/drift 推定と残留 σ。判定: σ < 2 ns (≈ 60 cm 相当, tdoa-design.md §6 の 2.)
# タグ模擬の blink_tx (addr を 0x0001 に変更) を追加した場合:
uv run python tools/tdoa/sync_analysis.py anchorA.csv anchorB.csv --tag-src 0x0001
```

解析ロジックは `--selftest`(合成クロック)で実機なしで検証済み。
結果は成立/不成立にかかわらず [tdoa-design.md](../docs/tdoa-design.md) §3 に実測値を記録する。

## タグ CSV 出力仕様

```
seq,ok,d_mm,elapsed_ms,exchange_us,err
```

- `exchange_us`: `requestDSRange()` 呼出し全体の実測時間(ホスト SPI 処理込み)。スロット設計はこちらを使う
- `elapsed_ms`: ライブラリが報告する所要時間
- `#` で始まる行はメタデータ/サマリ

## 実測レポートテンプレート

各検証の記録様式は [docs/reports/](../docs/reports/) にある(コピーして記入):
[Step 1 DS-TWR](../docs/reports/step1-ds-twr-report.md) /
[SS-TWR 対照](../docs/reports/ss-twr-report.md) /
[TDoA PoC](../docs/reports/tdoa-poc-report.md)

## B案: タグ上計算 (env:tag に統合, Issue #28)

本番モードのタグは `rtls/config/anchors`・`rtls/config/tuning` を受信すると
**タグ上解算 (rtls_solver) とオンボードセル選択**が有効になる。設定は NVS に
永続化され、Wi-Fi 断・再起動後も解算を継続する。設定未受信の間は ranges 送信のみ
(A案互換) で動作する。

**設定の配布** (サーバー側 PC から):

```bash
uv run python tools/publish_config.py    # server/config.yaml → rtls/config/# へ retained 配布
```

**動作モード** (NVS 永続。タグの USB シリアルにコマンドを送って切替):

| コマンド | モード | 出力 |
|---|---|---|
| `mode HYBRID` | 既定 | ranges + position を MQTT (A案サーバーと併用可、リプレイ資産も残る) |
| `mode QUIET` | 本番 | position のみ MQTT |
| `mode STANDALONE` | ロボット搭載 | UART (Serial1, 115200) へ 30 byte バイナリフレームのみ (tag-design.md §7) |
| `status` | — | 現在のモード・設定バージョン・ソルバー状態を表示 |

- タグ側 position には `"src":"tag"` が付く (サーバー解算の position と区別)
- SNTP 未同期時は 500 ms 周期のフリーランで測距する (単一タグ前提のフォールバック)
- UART ピンは `RTLS_UART_TX/RX` ビルドフラグで変更可
