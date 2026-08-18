# アプリケーション開発ガイド(測位結果の利用)

測位結果(タグの座標)を使うアプリケーションを作るためのガイド。
**サーバー・タグに手を入れず、購読者を追加するだけ**で開発できる(A案設計の狙い、server-design.md §5)。
実機がなくても仮想タグ([development.md](development.md) §4)で全インターフェースが動く。

## 1. 取得インターフェースの選択

| インターフェース | 向き先 | 特徴 |
|---|---|---|
| **MQTT** `rtls/tag/{addr}/position` | 機械間連携・常駐アプリ(推奨) | push 型、購読者をいくつでも追加可、QoS0・retain なし |
| WebSocket `ws://<server>:8000/ws` | Web UI・ダッシュボード | position / stats(2秒毎)/ truth(開発時)の3種を push |
| REST `GET /api/tags` ほか | スナップショット取得・ヘルスチェック | ポーリング型。`/api/floor`(アンカー・セル定義)、`/api/stats`(監視統計) |
| UART バイナリ(B案) | ロボット搭載(ROS 等) | タグ上計算の座標を 30 byte 固定フレームで直結。[tag-design.md](tag-design.md) §7 |

## 2. position メッセージ仕様

トピック: `rtls/tag/{addr}/position`(例 `rtls/tag/0x0001/position`)。ペイロード:

```json
{"tag": "0x0001", "t_ms": 1755212345690,
 "x_m": 12.34, "y_m": 8.76, "vx_ms": 0.51, "vy_ms": -0.12,
 "quality": {"n_anchors": 4, "residual_m": 0.03},
 "anchors_used": ["0x0010", "0x0011", "0x0013", "0x0014"],
 "anchors_rejected": [],
 "cell": "A", "state": "TRACKING"}
```

| フィールド | 意味 |
|---|---|
| `t_ms` | タグ側の測距時刻(SNTP 同期済み UNIX ms)。**受信時刻ではなくこちらを使う** |
| `x_m`, `y_m` | フロア座標 [m]。原点はフロア左下、x 右・y 上(`/api/floor` の寸法内) |
| `vx_ms`, `vy_ms` | カルマン推定速度 [m/s] |
| `quality.n_anchors` | 解算に使った距離数(COASTING では 0) |
| `quality.residual_m` | 解算の RMS 残差 [m] — 測位の信頼度指標 |
| `anchors_used` / `anchors_rejected` | 使用 / 棄却(NLoS・ゲート)されたアンカー |
| `cell` | 現在のセル(ヒステリシス付き判定) |
| `state` | 追尾状態(下表) |

### state の扱い(重要)

| state | 意味 | アプリでの扱いの定石 |
|---|---|---|
| `TRACKING` | 通常追尾(このエポックで解算成功) | すべての用途に使用可 |
| `COASTING` | 当該エポック欠測、カルマン予測のみ | 表示は可。**トリガ(ジオフェンス等)には使わない** |
| `STALE` | 2 秒以上解算なし | 警告表示。位置は古い予測 |
| `LOST` | 10 秒以上解算なし | 非表示にし「所在不明」として扱う |

### 品質ゲートの定石

クリティカルな判定(入退場、衝突警告など)は `state == "TRACKING"` かつ
`residual_m` が閾値以下(目安 0.5 m)のエポックだけで行う。
レイテンシ(測距→position 出版)は Wi-Fi + ブローカー + 解算で 20〜60 ms 程度の見積もり(server-design.md §14。実機では未計測)。

## 3. サンプルコード([examples/](../examples/))

どちらも仮想タグ環境でそのまま動作確認できる(実行例は各ファイル冒頭)。

- **[mqtt_subscriber.py](../examples/mqtt_subscriber.py)** — 最小の購読アプリ。
  position を購読して整形表示するだけの雛形
- **[geofence.py](../examples/geofence.py)** — 領域入退場検知。
  「TRACKING のみでトリガ」「品質ゲート」「退場ヒステリシス」というアプリ側の定石3点を実装した実例

```bash
# development.md §4 のスタック (mosquitto + server + virtual_tag) を起動した上で:
uv run python examples/mqtt_subscriber.py
uv run python examples/geofence.py --zone 0,0,25,25   # セル A への入退場を監視
```

ブラウザ側で使う場合(WebSocket)は `server/web/static/index.html` の
`connectWs()` がそのまま参考実装になる(`{"type":"position", ...}` を JSON で受ける)。

## 4. その他のトピック

| トピック | retain | 内容 |
|---|---|---|
| `rtls/tag/{addr}/ranges` | no | 生距離(アプリでは通常不要。独自解析やログ用) |
| `rtls/tag/{addr}/anchors` | **yes** | サーバー→タグの担当アンカー指示。**アプリは購読してよいが publish しない** |
| `rtls/sim/truth` | no | 仮想タグの真値(開発時のみ流れる)。精度評価アプリに利用可 |

## 5. 作法と注意

- **`rtls/` 名前空間へ publish しない**(購読のみ)。アプリ独自のトピックは別名前空間に置く
- position は retain されないため、起動直後の初期状態は `GET /api/tags` で取得してから購読に切り替えるとよい(UI と同じパターン)
- タグの追加・アンカー配置変更はサーバーの `config.yaml` だけで完結する。アプリはアドレスをハードコードせず `/api/floor` の `tags` を参照する
- 座標系はフロアローカル [m]。建物図面等への変換(回転・平行移動)はアプリ側の責務
- 複数アプリの同時購読は自由(MQTT の pub/sub がそのために選ばれている — 基本設計 §4.6)
