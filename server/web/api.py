"""Web API・WebSocket 配信 (server-design.md §9)。"""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from server.config import parse_addr

_STATIC = Path(__file__).parent / "static"


class Hub:
    """WebSocket 購読者への push 配信。"""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            with contextlib.suppress(Exception):
                await ws.send_json(message)


def create_app(server) -> FastAPI:
    """server: RtlsServer (循環 import 回避のため型注釈は付けない)。"""
    app = FastAPI(title="M5Stamp UWB RTLS")

    @app.get("/")
    async def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/api/floor")
    async def floor():
        cfg = server.config
        return {
            "width_m": cfg.floor.width_m,
            "height_m": cfg.floor.height_m,
            "anchors": {
                k: {"x": a.x, "y": a.y, "z": a.z} for k, a in cfg.anchors.items()
            },
            "cells": {
                name: {"rect": c.rect, "anchors": c.anchors}
                for name, c in cfg.cells.items()
            },
            "tags": cfg.tags,
            "sim_obstacles": server.sim_obstacles,  # 開発モード (無ければ空)
        }

    @app.get("/api/tags")
    async def tags():
        return {
            f"0x{tag:04X}": {
                "x_m": pos.x_m,
                "y_m": pos.y_m,
                "cell": pos.cell,
                "state": pos.state.name,
                "t_ms": pos.t_ms,
                "residual_m": pos.residual_m,
                "n_used": pos.n_used,
            }
            for tag, pos in server.latest.items()
        }

    @app.get("/api/stats")
    async def stats():
        return server.monitor.snapshot()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        await server.hub.add(ws)
        try:
            while True:
                await ws.receive_text()  # keepalive / ping 用 (内容は使わない)
        except WebSocketDisconnect:
            pass
        finally:
            await server.hub.remove(ws)

    # 参照だけ使う (lint 対策)
    _ = parse_addr
    return app
