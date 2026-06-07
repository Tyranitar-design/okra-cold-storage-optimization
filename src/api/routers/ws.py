"""WebSocket router — real-time channels for optimization, data changes, and route updates.

Supported channels:
  - optimization    : live solve progress / iteration events
  - data_changes    : node / route / config CRUD notifications
  - route_updates   : route status / delivery progress
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

logger = logging.getLogger("okra.ws_router")

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections grouped by channel.

    Each client subscribes to a single channel. The manager supports
    broadcasting JSON-serialisable messages to all subscribers of a channel.
    """

    _instance: "ConnectionManager | None" = None

    def __new__(cls) -> "ConnectionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialised", False):
            return
        self._initialised = True
        self._channels: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    @property
    def channels(self) -> dict[str, set[WebSocket]]:
        return self._channels

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._channels.setdefault(channel, set()).add(websocket)
        logger.info("WS connected: channel=%s, total=%d", channel, self._count_subscribers(channel))

    async def disconnect(self, websocket: WebSocket, channel: str) -> None:
        async with self._lock:
            if channel in self._channels:
                self._channels[channel].discard(websocket)
                if not self._channels[channel]:
                    del self._channels[channel]
        logger.info("WS disconnected: channel=%s", channel)

    async def broadcast(self, channel: str, message: dict[str, Any]) -> None:
        """Send a JSON message to all subscribers of a channel."""
        async with self._lock:
            clients = set(self._channels.get(channel, set()))

        stale: set[WebSocket] = set()
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:
                stale.add(ws)

        if stale:
            async with self._lock:
                for ws in stale:
                    self._channels.get(channel, set()).discard(ws)

    def _count_subscribers(self, channel: str) -> int:
        return len(self._channels.get(channel, set()))


# Singleton
manager = ConnectionManager()

# Valid channels
VALID_CHANNELS = {"optimization", "data_changes", "route_updates"}


def validate_token(token: str) -> bool:
    """Quick JWT validation — returns True if the token is parseable and not expired."""
    try:
        from src.api.auth import SECRET_KEY, ALGORITHM

        import jwt as _jwt

        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        _sub = payload.get("sub")
        return bool(_sub)
    except Exception:
        return False


# ── WS /ws/{channel} ───────────────────────────────────────────
@router.websocket("/{channel}")
async def websocket_endpoint(
    websocket: WebSocket,
    channel: str,
    token: str = Query(""),
):
    """
    WebSocket connection endpoint.

    Parameters:
      - channel : one of 'optimization', 'data_changes', 'route_updates'
      - token   : valid JWT access token (query parameter)

    The server echoes received messages back to the sender and broadcasts
    them to the channel.  Additionally, lifecycle events (collect/left)
    are broadcast to all members.
    """
    if channel not in VALID_CHANNELS:
        await websocket.close(code=4004, reason=f"Invalid channel '{channel}'. Valid: {', '.join(sorted(VALID_CHANNELS))}")
        return

    if not token:
        await websocket.close(code=4001, reason="Missing 'token' query parameter")
        return

    if not validate_token(token):
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await manager.connect(websocket, channel)

    await manager.broadcast(
        channel,
        {"type": "system", "event": "join", "channel": channel, "subscribers": manager._count_subscribers(channel)},
    )

    try:
        while True:
            data = await websocket.receive_json()
            # Echo back to sender
            await websocket.send_json({"type": "echo", "original": data})

            # Optionally broadcast to the channel (let the client decide via "broadcast" flag)
            if isinstance(data, dict) and data.get("broadcast"):
                del data["broadcast"]
                await manager.broadcast(channel, {"type": "message", "sender": "user", "data": data})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS error on channel %s: %s", channel, exc)
    finally:
        await manager.disconnect(websocket, channel)
        await manager.broadcast(
            channel,
            {"type": "system", "event": "leave", "channel": channel, "subscribers": manager._count_subscribers(channel)},
        )


# ── Helper: broadcast data_change events (called by other routers) ──
async def broadcast_data_change(event: str, payload: dict[str, Any]) -> None:
    """Broadcast a data-change event to all subscribers of the 'data_changes' channel."""
    import asyncio as _asyncio

    try:
        await manager.broadcast(
            "data_changes",
            {"type": "data_change", "event": event, "data": payload, "timestamp": _asyncio.get_event_loop().time()},
        )
    except Exception:
        pass
