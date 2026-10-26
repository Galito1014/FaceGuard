"""Difusión de eventos en tiempo real por WebSocket.

Los hilos de cámara/procesamiento llaman a `hub.publish()`; el mensaje se
entrega a cada cliente conectado desde el bucle de asyncio.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("faceguard.ws")


class Hub:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, dict[str, Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket, user: dict[str, Any]) -> None:
        await ws.accept()
        self._clients[ws] = user

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.pop(ws, None)

    @property
    def count(self) -> int:
        return len(self._clients)

    async def _broadcast(self, message: dict[str, Any]) -> None:
        perm = message.pop("_perm", None)
        data = json.dumps(message, ensure_ascii=False, default=str)
        from app.core.security import has_perm  # import diferido: evita ciclo

        for ws, user in list(self._clients.items()):
            if perm and not has_perm(user, perm):
                continue
            try:
                await ws.send_text(data)
            except Exception:  # cliente desconectado
                self.disconnect(ws)

    def publish(self, type_: str, payload: Any, perm: str | None = None) -> None:
        """Seguro para llamar desde cualquier hilo."""
        if not self._loop or not self._clients:
            return
        msg = {"type": type_, "data": payload, "_perm": perm}
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)
        except RuntimeError:
            pass


hub = Hub()
