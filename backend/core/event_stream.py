"""
Event Stream — bridges EventBus + SystemState to external WebSocket clients.
Handles subscriptions, state diffing, and broadcast to multiple clients.

Thread-safe: accepts events from non-async threads via asyncio.run_coroutine_threadsafe.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from core.event_bus import EventBus
from core.system_state import SystemState
from services.logger import info, error


class EventStream:
    """
    Listens to EventBus events, computes state diffs,
    and broadcasts updates to all connected WebSocket clients.
    """

    def __init__(
        self,
        event_bus: EventBus,
        system_state: SystemState,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._bus = event_bus
        self._state = system_state
        self._clients: set[WebSocket] = set()
        self._last_state: dict[str, Any] = {}
        self._loop: asyncio.AbstractEventLoop | None = loop

    # ── Client management ─────────────────────────────────────────────

    async def connect(self, ws: WebSocket) -> None:
        self._clients.add(ws)
        info(f"WebSocket client connected ({len(self._clients)} total)")

        # Send immediate full state snapshot on connect
        current = self._state.get_state()
        self._last_state = dict(current)
        await self._send(ws, "state_update", current)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        info(f"WebSocket client disconnected ({len(self._clients)} remaining)")

    # ── EventBus subscriptions (called from Processor — may be non-async) ──

    def on_event(self, event: str, data: dict) -> None:
        """
        Called whenever a new event occurs (from any thread).
        Computes a diff against the previous state and broadcasts changes.
        """
        current = self._state.get_state()
        diff = self._compute_diff(self._last_state, current)
        self._last_state = dict(current)

        # Schedule broadcasts on the event loop thread-safe
        if diff:
            self._schedule_broadcast("state_update", diff)

        self._schedule_broadcast("event", {"event": event, "data": data})

    # ── Heartbeat ─────────────────────────────────────────────────────

    async def heartbeat_loop(self, interval: float = 5.0) -> None:
        """Send a heartbeat message every `interval` seconds."""
        while True:
            await asyncio.sleep(interval)
            if self._clients:
                await self._broadcast(
                    "heartbeat",
                    {"timestamp": datetime.now(timezone.utc).isoformat()},
                )

    # ── Internal broadcast / send ─────────────────────────────────────

    def _schedule_broadcast(self, msg_type: str, data: dict) -> None:
        """Schedule a broadcast on the async event loop thread-safe."""
        loop = self._loop or asyncio.get_event_loop()
        if loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(
            self._broadcast(msg_type, data), loop
        )

    async def _broadcast(self, msg_type: str, data: dict) -> None:
        """Send a message to every connected client."""
        payload = json.dumps({"type": msg_type, "data": data})
        stale: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_text(payload)
            except RuntimeError as e:
                if "not connected" in str(e) or "close" in str(e).lower():
                    stale.append(ws)
                else:
                    stale.append(ws)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)

    async def _send(self, ws: WebSocket, msg_type: str, data: dict) -> None:
        """Send a message to a single client."""
        try:
            await ws.send_text(json.dumps({"type": msg_type, "data": data}))
        except Exception:
            pass

    # ── State diffing ─────────────────────────────────────────────────

    def _compute_diff(self, old: dict, new: dict) -> dict[str, Any]:
        """Return only the keys that changed between old and new state."""
        diff: dict[str, Any] = {}
        for key in new:
            if key not in old or old[key] != new[key]:
                diff[key] = new[key]
        return diff
