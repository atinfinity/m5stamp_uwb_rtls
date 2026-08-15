# 開発環境構築手順

実機(M5Stamp C5 + Stamp UWB F)が無くても、測位サーバー・シミュレータ・ファームウェアのビルド検証まで全て動かせる。実機を使う手順は [firmware/README.md](../firmware/README.md) を参照。

## 1. 必要なツール

| ツール | 用途 | macOS | Ubuntu |
|---|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python パッケージ管理(必須) | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Mosquitto | MQTT ブローカー(ライブ実行時) | `brew install mosquitto` | `sudo apt install mosquitto` |
| C++17 コンパイラ | FW 共通ロジックのネイティブテスト | `xcode-select --install` | `sudo apt install g++` |
| [PlatformIO](https://platformio.org/) | FW ビルド(ESP32-C5) | `brew install platformio` | `uv tool install platformio` |
| ffmpeg | デモ GIF の生成(任意) | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| gh | Issue/PR 操作(任意) | `brew install gh` | [cli.github.com](https://cli.github.com/) |

Python 本体は uv が自動で用意する(`requires-python >= 3.11`。3.14 で動作確認済み)。

## 2. セットアップ

```bash
git clone https://github.com/atinfinity/m5stamp_uwb_rtls.git
cd m5stamp_uwb_rtls
uv sync --all-extras     # .venv 作成 + 全依存 (mqtt/web extras + dev グループ)
```

## 3. テストを回す(CI と同じ内容)

```bash
uv run pytest                     # Python 30 テスト (解算・セル・Web API・e2e 回帰・C++ 一致試験)
./firmware/test_native/run.sh     # FW 共通ロジック (スロット/JSON) + C++ ソルバーのホストテスト
pio run -d firmware/anchor        # アンカー FW の ESP32-C5 ビルド (実機不要、初回はツールチェーン取得で数分)
pio run -d firmware/tag           # タグ FW (本番 env:tag + 計測 env:tag_step1 の両方)
```

- `uv run pytest` には **C++ 一致試験**(`tests/test_cpp_parity.py`)が含まれ、`c++` コンパイラを使って
  `firmware/lib/rtls_solver` をビルド・実行する。Python 実装と C++ 実装のどちらかだけを変更すると失敗する
  (tag-design.md §10-2 のルールを CI が強制)。

## 4. ライブ実行(仮想タグで end-to-end)

ターミナルを3つ使う:

```bash
# ① MQTT ブローカー
mosquitto

# ② 測位サーバー + Web UI
uv run python -m server.app --config server/config.yaml

# ③ 仮想タグ (シミュレータを実時間で MQTT へ流す)
uv run python tools/virtual_tag.py
```

ブラウザで http://localhost:8000 を開くと、フロアマップにタグ位置・軌跡・真値(GT)・
棄却測距・監視パネルが表示される(凡例は画面下部)。

- タグ数・アンカー配置・チューニングは `server/config.yaml` で変更
- 仮想タグの劣化条件(NLoS 率など)は `server/simulate.py` の `SimParams` を参照
- ポート競合時: `mosquitto -p 1899` + config の `mqtt.port` 変更 + `--http-port 8099`

## 5. オフライン解析(シミュレータ → リプレイ)

```bash
uv run python tools/simulate.py --config server/config.yaml --duration-s 120 \
    --out logs/sim_ranges.jsonl --truth logs/sim_truth.jsonl
uv run python -m server.replay logs/sim_ranges.jsonl --out logs/positions.jsonl
```

チューニング(`config.yaml` の `tuning:`)を変えて同じ JSONL をリプレイすれば、
実測なしでアルゴリズム変更を評価できる(server-design.md §8)。

## 6. リポジトリ構成の要点

```
docs/            設計書 (基本設計 rtls-design.md から辿れる)
server/          測位サーバー (Python) — pipeline は MQTT 非依存でテスト可能
firmware/
  anchor/ tag/   PlatformIO プロジェクト (ESP32-C5)
  lib/rtls_common/   ハード非依存の共有ロジック (TDMA スロット・ペイロード)
  lib/rtls_solver/   B案 C++ ソルバー (Python 実装と一致試験で同期)
  test_native/   ホストで走る C++ テスト
tools/           シミュレータ・仮想タグ・Step1 計測ツール
tests/           pytest (e2e 回帰・C++ 一致試験含む)
```

## 7. 開発フロー

1. Issue を立てる → `feature/...` ブランチを切る
2. 変更 + テスト(§3 の4コマンドがローカルで通ること)
3. PR を作成 → CI(python / firmware-native / firmware ×2)が green になってからマージ
4. 解算アルゴリズムを触る場合は **Python と C++ を必ず同時に変更**(一致試験が落ちる)

## トラブルシュート

| 症状 | 原因と対処 |
|---|---|
| ブラウザで UI が "disconnected" のまま | `uv sync --all-extras` を実行したか確認(WebSocket は `websockets` パッケージが必要。web extras に含まれる) |
| `pio run` が board 不明で失敗 | pioarduino platform の取得失敗。ネットワークを確認して `pio run` を再実行(URL は各 platformio.ini に記載) |
| 一致試験だけ失敗する | Python か C++ の片側だけ解算を変更していないか確認。両方直すか revert する |
| ポート 1883/8000 が使用中 | §4 のポート変更手順を使う |
