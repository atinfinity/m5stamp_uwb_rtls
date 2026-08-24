# ファームウェア

| 対象 | env | 内容 |
|---|---|---|
| `tag`(本番) | `tag` | アンカー巡回 + TDMA + Wi-Fi/MQTT(Step 2/3、Issue [#6](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/6)) |
| `tag`(計測) | `tag_step1` | 1対1 DS-TWR + CSV出力(Step 1、Issue [#1](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/1)) |
| `tag`(計測・SS) | `tag_step1_ss` | 1対1 SS-TWR検証(Issue [#14](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/14)) |
| `anchor` | `anchor` | DS-TWR応答専用 |
| `anchor`(SS) | `anchor_ss` | SS-TWR応答(検証用) |
| `tdoa_poc` | `blink_tx` / `listener` | TDoA PoC: 周期ブリンク送信 / RXタイムスタンプ計測(Issue [#16](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/16)) |

Arduino非依存ロジック(TDMAスロット判定・MQTTペイロード生成/解析)は`lib/rtls_common/`にあり、
`./test_native/run.sh`でホスト上の単体テストが実行できる(CIでも実行)。

## 本番モード(env:tag)

Wi-Fi / MQTT / SNTPの接続先は`firmware/tag/platformio.ini`の`build_flags`で指定する
(`WIFI_SSID` / `WIFI_PASS` / `MQTT_HOST`。SNTPは既定でMQTT_HOSTのchronyを使用 — 基本設計 §4.9)。

```bash
cd firmware/tag
pio run -e tag -t upload          # 本番モード
pio run -e tag_step1 -t upload    # Step 1 計測モード
```

動作: SNTP同期後、自スロット(アドレスから決まる90 ms窓、スーパーフレーム500 ms)で
担当アンカー4台へ順次DS-TWR → `rtls/tag/{addr}/ranges`へpublish。
`rtls/tag/{addr}/anchors`(retained)を受信すると担当リストを差し替える(セルハンドオーバー)。

---

# Step 1: DS-TWR 1対1実測

Issue [#1](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/1) / 設計: [ds-twr-design.md](../docs/ds-twr-design.md) §6

## ハードウェア準備

- M5Stamp C5 + Stamp UWB Fを**2セット**。各セットは付属の0.5mm-12P FPCケーブルで直結(ピン割当は自動で`rtls_common.h`と一致)。組み立ての詳細は[docs/hardware.md](../docs/hardware.md)を参照
- 両ノードUSB-CでPCへ接続(タグ側は計測ログの採取にシリアルを使う)
- アンテナ端が金属・机面に近づかないよう治具等で浮かせる(基本設計 §3.3)

## ビルドと書き込み

ESP32-C5のArduinoサポートはpioarduino版platformを使用(platformio.ini設定済み)。

```bash
# アンカー (addr 0x0010)
cd firmware/anchor
pio run -t upload

# タグ計測モード (addr 0x0001 → anchor 0x0010 へ 50ms 間隔で測距)
cd ../tag
pio run -e tag_step1 -t upload
```

アドレス・測距間隔は各`platformio.ini`の`build_flags`(`NODE_ADDR` / `TARGET_ANCHOR` / `RANGE_INTERVAL_MS`)で変更する。

> **注**: board定義は汎用の`esp32-c5-devkitc-1`を使用している。書き込みに失敗する場合は
> `pio device list`でポートを確認し、`upload_port`を明示すること。

## 計測手順(ds-twr-design.md §6の1. と2.)

1. 既知距離(レーザー距離計で測定)にタグ・アンカーを設置(高さを揃える)
2. タグのシリアルをcapture.pyで採取:

```bash
uv run --with pyserial python tools/step1/capture.py --port /dev/tty.usbmodemXXXX \
    --true-dist-m 5.000 --count 1000 --out logs/dist5m.csv
```

3. 距離を変えて繰り返し(1 / 5 / 10 / 20 / 40 m)
4. 解析:

```bash
uv run python tools/step1/analyze.py logs/dist*.csv
```

出力(成功率、bias、σ、交換時間p50/p95/p99)をIssue [#1](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/1)に記録し、以下を更新する:

- `bias_mm`校正値 → server設計 §10のconfig.yamlへ
- 交換時間p95 → 基本設計 §4.4のTDMAスロット幅
- `rtls_common.h`のタイミング定数 — アンカーの応答遅延はライブラリ設定`responseTxDelayUus`に
  代入される定数`kDsResponseTxDelayUus`で決まる。3000→1500 µsに詰める実験は、この定数を
  変更して同手順で比較する

## SS-TWR検証(Issue [#14](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/14)、ss-twr-design.md §4/§6)

DS-TWRの対照試験として、**同じ設置・同じ距離**でenvをSSに替えて同手順を繰り返す:

```bash
cd firmware/anchor && pio run -e anchor_ss -t upload      # アンカーを SS 応答に
cd ../tag && pio run -e tag_step1_ss -t upload            # タグを SS 計測に
# capture.py / analyze.py は共通 (mode は CSV メタデータから自動判別)
uv run python tools/step1/analyze.py logs/ds_dist5m.csv logs/ss_dist5m.csv   # DS/SS を並べて比較
```

判定(3条件すべて満たしたらSS-TWRを予備方式として有効化):

| # | 条件 | 見方 |
|---|---|---|
| ① | σ ≤ 15 cm・バイアス ≤ 10 cm | **CFO補償の有無がここで判明**。補償なしならm級誤差が出て即不成立(ss-twr-design.md §2.2) |
| ② | 交換時間がDS比30% 以上短い | analyze.pyのp50を比較 |
| ③ | リプレイでCEP50 ≤ 30 cm維持 | Step 2以降のログで確認 |

- biasは方式ごとに異なりうるため、**DS/SS別々に校正値を記録**する
- 温度依存(始動直後vs 30分後)もss-twr-design.md §6の1. に従い両方式で採取する
- 不成立の場合は実測値をss-twr-design.mdに追記してIssue [#14](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/14)をclose

## TDoA PoC(Issue [#16](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/16)、tdoa-design.md §6)

将来方式TDoAのゲート条件を検証する。公開APIにRXタイムスタンプが無いため、
listener FWは同梱`qm33120w_sdk`の`dwt_readrxtimestamp()`を直叩きする
(40 bit、1 tick ≈ 15.65 ps、~17.2 sで周回)。

**PoC-1(2ノード): タイムスタンプ取得可否**

```bash
cd firmware/tdoa_poc
pio run -e blink_tx -t upload    # ノード1: 100ms 毎にブリンク送信 (addr 0x00F0)
pio run -e listener -t upload    # ノード2: 受信 + "src,seq,rx_ticks" を CSV 出力
```

判定: listenerの`rx_ticks`がブリンクごとに**単調増加**していれば取得成功
(増加しない/常に同値なら`receiveFrame()`実装がレジスタを上書きしており、ライブラリ改造が必要)。

**PoC-2(3ノード): 2アンカー無線同期**

blink_tx 1台 + listener 2台(それぞれPCにシリアル接続しCSVを採取)で:

```bash
uv run python tools/tdoa/sync_analysis.py anchorA.csv anchorB.csv
# → クロック offset/drift 推定と残留 σ。判定: σ < 2 ns (≈ 60 cm 相当, tdoa-design.md §6 の 2.)
# タグ模擬の blink_tx (addr を 0x0001 に変更) を追加した場合:
uv run python tools/tdoa/sync_analysis.py anchorA.csv anchorB.csv --tag-src 0x0001
```

解析ロジックは`--selftest`(合成クロック)で実機なしで検証済み。
結果は成立/不成立にかかわらず[tdoa-design.md](../docs/tdoa-design.md) §3に実測値を記録する。

## タグCSV出力仕様

```
seq,ok,d_mm,elapsed_ms,exchange_us,err
```

- `exchange_us`: `requestDSRange()`呼出し全体の実測時間(ホストSPI処理込み)。スロット設計はこちらを使う
- `elapsed_ms`: ライブラリが報告する所要時間
- `#`で始まる行はメタデータ/サマリ

## 実測レポートテンプレート

各検証の記録様式は[docs/reports/](../docs/reports/)にある(コピーして記入):
[Step 1 DS-TWR](../docs/reports/step1-ds-twr-report.md) /
[SS-TWR対照](../docs/reports/ss-twr-report.md) /
[TDoA PoC](../docs/reports/tdoa-poc-report.md)

## B案: タグ上計算(env:tagに統合, Issue [#28](https://github.com/atinfinity/m5stamp_uwb_rtls/issues/28))

本番モードのタグは`rtls/config/anchors`・`rtls/config/tuning`を受信すると
**タグ上解算(rtls_solver)とオンボードセル選択**が有効になる。設定はNVSに
永続化され、Wi-Fi断・再起動後も解算を継続する。設定未受信の間はranges送信のみ
(A案互換)で動作する。

**設定の配布** (サーバー側PCから):

```bash
uv run python tools/publish_config.py    # server/config.yaml → rtls/config/# へ retained 配布
```

**動作モード** (NVS永続。タグのUSBシリアルにコマンドを送って切替):

| コマンド | モード | 出力 |
|---|---|---|
| `mode HYBRID` | 既定 | ranges + positionをMQTT (A案サーバーと併用可、リプレイ資産も残る) |
| `mode QUIET` | 本番 | positionのみMQTT |
| `mode STANDALONE` | ロボット搭載 | UART (Serial1, 115200)へ30 byteバイナリフレームのみ(tag-design.md §7) |
| `status` | — | 現在のモード・設定バージョン・ソルバー状態を表示 |

- タグ側positionには`"src":"tag"`が付く(サーバー解算のpositionと区別)
- SNTP未同期時は500 ms周期のフリーランで測距する(単一タグ前提のフォールバック)
- UARTピンは`RTLS_UART_TX/RX`ビルドフラグで変更可
