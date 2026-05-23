"""
Event Bus — central in-memory pub/sub communication system.
"""

from collections import defaultdict
from typing import Callable, Any

from services.logger import info


EventCallback = Callable[[str, Any], None]


class EventBus:
    """Simple publish-subscribe event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventCallback]] = defaultdict(list)

    def subscribe(self, event: str, callback: EventCallback) -> None:
        self._subscribers[event].append(callback)
        info(f"Subscribed to event '{event}'")

    def unsubscribe(self, event: str, callback: EventCallback) -> None:
        listeners = self._subscribers.get(event, [])
        if callback in listeners:
            listeners.remove(callback)
            info(f"Unsubscribed from event '{event}'")

    def emit(self, event: str, data: Any = None) -> None:
        info(f"Emitting event '{event}'")
        for callback in self._subscribers.get(event, []):
            callback(event, data)
