"""Narrow per-plugin host context. Not a handle to the old application."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from hermes_host.metadata import PluginMetadata
from hermes_host.policy import FailClosedPolicy, PrivilegePolicy


class HostContext:
    """The only object a plugin ``register()`` function receives from the kernel."""

    def __init__(
        self,
        *,
        host_id: str,
        metadata: PluginMetadata,
        data_dir: Path,
        settings: Mapping[str, Any],
        registry: Any,
        events: Any,
        cancelled: threading.Event,
        policy: PrivilegePolicy,
        allowed_service_owners: Mapping[str, tuple[str, ...]],
        log: logging.Logger,
    ) -> None:
        self._host_id = host_id
        self._metadata = metadata
        self._data_dir = data_dir
        self._settings = dict(settings)
        self._registry = registry
        self._events = events
        self._cancelled = cancelled
        self._policy = policy
        self._allowed_service_owners = allowed_service_owners
        self._log = log
        self._start_hooks: list[Callable[[], None]] = []

    @property
    def plugin_id(self) -> str:
        return self._metadata.id

    @property
    def plugin_version(self) -> str:
        return self._metadata.version

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def data_dir(self) -> Path:
        """Writable per-plugin data. Distinct from the plugin install directory."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        return self._data_dir

    def settings(self) -> Mapping[str, Any]:
        return dict(self._settings)

    def log(self) -> logging.Logger:
        return self._log

    def register_service(self, name: str, implementation: Any, *, unique: bool = True) -> None:
        self._registry.register(
            name,
            implementation,
            plugin_id=self.plugin_id,
            unique=unique,
            allowed_owners=self._allowed_service_owners.get(name),
        )

    def get_service(self, name: str) -> Any:
        return self._registry.get(name)

    def find_service(self, name: str) -> Any | None:
        return self._registry.find(name)

    def list_services(self, name: str) -> tuple[Any, ...]:
        return self._registry.all(name)

    def on_start(self, callback: Callable[[], None]) -> None:
        if not callable(callback):
            raise TypeError("on_start callback must be callable")
        self._start_hooks.append(callback)

    def on_stop(self, callback: Callable[[], None]) -> None:
        if not callable(callback):
            raise TypeError("on_stop callback must be callable")
        self._registry.add_cleanup(self.plugin_id, callback)

    def subscribe(self, event: str, handler: Callable[[str, dict[str, Any]], None]) -> None:
        self._events.subscribe(self.plugin_id, event, handler)

    def emit(self, event: str, **payload: Any) -> None:
        self._events.emit(event, payload)

    def authorize(self, operation: str, **details: Any) -> None:
        """Host-mediated privileged operations. Missing policy is deny."""
        policy: PrivilegePolicy = self._policy or FailClosedPolicy()
        policy.authorize(self.plugin_id, operation, dict(details))

    def wait_cancelled(self, timeout: float | None = None) -> bool:
        return self._cancelled.wait(timeout)

    def start_hooks(self) -> tuple[Callable[[], None], ...]:
        return tuple(self._start_hooks)
