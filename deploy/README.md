# 常設デプロイ (Docker Compose)

MQTT ブローカー(Mosquitto)と測位サーバー + Web UI を一括起動する。
Raspberry Pi 等での常設運用を想定(server-design.md §2)。

```bash
cd deploy
docker compose up -d --build
```

- Web UI: http://localhost:8000
- MQTT: ホストの 1883 番(アンカー/タグ/仮想タグはここへ接続)
- 設定: `server/config.yaml` を読み取り専用でマウント(`mqtt.host` はコンテナ内で
  `--mqtt-host mosquitto` により自動上書き)。変更後は `docker compose restart server`
- 生距離ログ: named volume `rtls-logs` に日次 JSONL で蓄積
  (`docker compose cp server:/app/logs ./logs-export` で取り出し)

動作確認(ホスト側から仮想タグを流す):

```bash
uv run python tools/virtual_tag.py     # localhost:1883 → コンテナ内サーバーが解算
```

停止: `docker compose down`(ログ volume は保持。消す場合は `down -v`)
