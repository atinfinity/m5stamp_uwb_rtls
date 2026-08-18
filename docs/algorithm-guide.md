# 測位アルゴリズム開発ガイド

解算パイプライン(補正・外れ値除去・ソルバー・フィルタ)を改良するためのガイド。
**実機は不要** — 開発ループはすべてシミュレータとリプレイで回る。

- 仕様の正: [server-design.md](server-design.md) §5(処理段)/ [tag-design.md](tag-design.md) §4(C++ 差分)
- 環境構築: [development.md](development.md)

## 1. アルゴリズムはどこにあるか

同じアルゴリズムが **2 実装**ある。挙動を変える変更は必ず両方に入れる(§5)。

| 処理段 | Python (A案・正) | C++ (B案・タグ上) |
|---|---|---|
| 高低差補正 | `server/positioning/geometry.py` | `firmware/lib/rtls_solver/geometry.hpp` |
| ゲーティング | `server/positioning/outlier.py` | `firmware/lib/rtls_solver/outlier.hpp` |
| 最小二乗ソルバー | `geometry.py: solve_2d` | `geometry.hpp: solve2d` |
| カルマンフィルタ | `server/positioning/kalman.py` | `firmware/lib/rtls_solver/kalman.hpp` |
| パイプライン統合・状態機械・leave-one-out | `server/positioning/pipeline.py` | `firmware/lib/rtls_solver/pipeline.hpp` |
| チューニングパラメータ | `server/config.yaml` の `tuning:` | `pipeline.hpp: struct Tuning`(既定値を一致させる) |

**まず Python で開発し、確定してから C++ へ移植する**のが基本フロー(tag-design.md §11)。

## 2. 開発ループ(シミュレータ → リプレイ → 評価)

すべて決定的(seed 固定)なので、変更の効果を再現可能に比較できる。

```bash
# ① 合成データを一度だけ生成(真値付き)
uv run python tools/simulate.py --config server/config.yaml --duration-s 300 \
    --seed 42 --out logs/dev_ranges.jsonl --truth logs/dev_truth.jsonl

# ② アルゴリズムや config.yaml の tuning を変更

# ③ リプレイして評価
uv run python -m server.replay logs/dev_ranges.jsonl --out logs/dev_positions.jsonl
```

評価(CEP など)はテストと同じ指標を使う。ワンライナー:

```bash
uv run python - <<'EOF'
import json, math
truth = {}
for l in open("logs/dev_truth.jsonl"):
    d = json.loads(l); truth[(d["tag"], d["t_ms"])] = (d["x"], d["y"])
errs = []
for l in open("logs/dev_positions.jsonl"):
    d = json.loads(l)
    if d["state"] != "TRACKING": continue
    t = truth.get((d["tag"], d["t_ms"]))
    if t: errs.append(math.hypot(d["x_m"]-t[0], d["y_m"]-t[1]))
errs.sort(); n = len(errs)
print(f"n={n} CEP50={errs[n//2]*100:.1f}cm CEP95={errs[int(n*.95)]*100:.1f}cm max={errs[-1]*100:.1f}cm")
EOF
```

劣悪条件での頑健性は `SimParams` を振って確認する(`tools/simulate.py --nlos-prob 0.2 --dropout-prob 0.1` 等)。
チューニングのグリッド探索は **`tools/sweep.py`** で機械化できる
(`--param tuning.residual_gate_m=0.3,0.5,0.7` の直積を一括評価し CEP 表を出力。真値なしの実測ログにも対応)。
テストスイートにも同じ回帰が入っている: `uv run pytest tests/test_e2e_replay.py -s`(CEP を print する)。

## 3. 変更の種類別ガイド

### チューニングのみ(コード変更なし)

`server/config.yaml` の `tuning:` を変えてリプレイ。対象: ゲート幅(`v_max_ms`, `gate_margin_m`)、
外れ値閾値(`residual_gate_m`)、フィルタ雑音(`sigma_a`, `sigma_m_floor`)、状態遷移(`stale_sec`, `lost_sec`)。
確定値は C++ の `Tuning` 既定値にも反映する。

### フィルタの変更(例: CA モデル、適応ノイズ)

`kalman.py` を変更 → `tests/test_kalman.py` を更新 → §2 で効果を確認 → `kalman.hpp` へ移植。
インターフェース(`init/predict/update/state`)を保てば pipeline 側は無変更で済む。

### ソルバーの変更(例: 重み付け変更、3D 化)

`geometry.solve_2d` を変更。縮退検出(共線)と発散ガードを外さないこと。
C++ 側 `solve2d` は scipy が使えないため IRLS で近似している — 反復条件を変えると一致試験の
乖離が広がるので、変更後に §5 の許容値を実測し直す。

### 外れ値除去・状態機械の変更

`pipeline.py` の `_usable_ranges` / `_solve` / `process`。状態機械
(INIT/TRACKING/COASTING/STALE/LOST)を変える場合は `tests/test_pipeline.py` の
該当ケース(欠測・重複 seq・鮮度・タグ再起動・LOST 再捕捉)を必ず更新する。

### 観測モデル自体の変更(TDoA 化など)

pipeline の入出力型(`RangeSet` → `Position`)を保てばサーバー側(MQTT/UI)は無変更で動く。
大規模変更は設計書([tdoa-design.md](tdoa-design.md) 等)を先に更新する。

## 4. 品質ゲート(変更を出す前に)

```bash
uv run pytest                     # 単体 + e2e 回帰 + C++ 一致試験
./firmware/test_native/run.sh     # C++ 側の単体テスト
```

受入基準(server-design.md §13): 標準条件で CEP50 ≤ 0.30 m、TRACKING 中の 1 エポック 2 m 超ジャンプなし、
NLoS 20% でも CEP50 ≤ 0.5 m。現状の実力は CEP50 ≈ 4–5 cm なので、**明確な理由なく悪化させない**。

## 5. Python / C++ 一致試験のルール

`tests/test_cpp_parity.py` が同一入力に対する両実装の出力を突き合わせる
(許容: 中央値 ≤ 1 cm・p99 ≤ 2 cm・最大 ≤ 10 cm・状態一致 ≥ 99%、tag-design.md §10 の 2.)。

- **片側だけ変更すると CI が落ちる**。これは仕様(意図的なガード)
- 正当な変更で許容値を超える場合: 両実装を修正 → 乖離を実測 → 妥当なら
  tag-design.md §10 の 2. の許容値と test の閾値を実測値ベースで更新(コミットメッセージに根拠を書く)

## 6. 実測データでの開発(実機導入後)

サーバーは受信した生距離を `logs/ranges-YYYYMMDD.jsonl` に常時記録している(recorder)。
実測ログはそのまま §2 のリプレイに入る — **アルゴリズム変更の評価に実機の再測定は不要**。
代表シーンのログを `tests/fixtures/` に置き、回帰テスト化するのが Step 2 以降の運用
(server-design.md §13 の 3.)。アンカー別バイアス校正は `config.yaml` の `bias_mm`(基本設計 §6)。

## チェックリスト

- [ ] Python と C++ の両方を変更した(または挙動に影響しないことを確認した)
- [ ] `uv run pytest` と `./firmware/test_native/run.sh` が通る
- [ ] 標準条件 + 劣悪条件(NLoS 20%)のリプレイで CEP が悪化していない
- [ ] チューニング既定値を変えた場合、config.yaml と C++ `Tuning` の両方を更新した
- [ ] 設計書と実装が乖離する変更は設計書側も更新した
