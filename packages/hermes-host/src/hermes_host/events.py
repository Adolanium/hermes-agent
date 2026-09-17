"""Small typed-enough event bus. Notifications only; request/response uses services."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from hermes_host.errors import PluginError

Handler = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[str, Handler]]] = defaultdict(list)

    def subscribe(self, plugin_id: str, event: str, handler: Handler) -> None:
        if not event or not callable(handler):
            raise PluginError(f"plugin {plugin_id!r} subscribed with an invalid event handler")
        self._handlers[event].append((plugin_id, handler))

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        for _plugin_id, handler in list(self._handlers.get(event, ())):
            handler(event, payload)

    def drop_plugin(self, plugin_id: str) -> None:
        for event, handlers in list(self._handlers.items()):
            self._handlers[event] = [item for item in handlers if item[0] != plugin_id]
            if not self._handlers[event]:
                del self._handlers[event]
