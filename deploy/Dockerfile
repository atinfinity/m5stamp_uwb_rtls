# 測位サーバーのコンテナイメージ (Issue #18 / server-design.md §2)
# ビルドコンテキストはリポジトリルート (deploy/docker-compose.yml が指定)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy

# 依存だけ先に解決してレイヤキャッシュを効かせる
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra mqtt --extra web --no-install-project

COPY server ./server
RUN uv sync --frozen --no-dev --extra mqtt --extra web

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "python", "-m", "server.app", \
     "--config", "/app/config/config.yaml", "--http-port", "8000", \
     "--log-dir", "/app/logs", "--mqtt-host", "mosquitto"]
