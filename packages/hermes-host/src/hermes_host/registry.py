"""Per-host service registry. No process-global tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from hermes_host.errors import CapabilityError, PluginError


@dataclass
class ServiceRecord:
    name: str
    plugin_id: str
    implementation: Any
    unique: bool


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, list[ServiceRecord]] = {}
        self._cleanups: list[tuple[str, Callable[[], None]]] = []

    def register(
        self,
        name: str,
        implementation: Any,
        *,
        plugin_id: str,
        unique: bool = True,
        allowed_owners: tuple[str, ...] | None = None,
    ) -> None:
        if not name or not isinstance(name, str):
            raise PluginError(f"plugin {plugin_id!r} registered an invalid service name")
        if unique and allowed_owners is not None and plugin_id not in allowed_owners:
            # Explicit selection chose another implementation; do not publish this one.
            return
        existing = self._services.setdefault(name, [])
        if unique and any(record.unique for record in existing):
            raise CompositionError(
                f"unique service {name!r} is already registered by {existing[0].plugin_id!r}"
            )
        existing.append(
            ServiceRecord(name=name, plugin_id=plugin_id, implementation=implementation, unique=unique)
        )

    def get(self, name: str) -> Any:
        records = self._services.get(name) or []
        if not records:
            raise CapabilityError(f"required service {name!r} is not available in this composition")
        return records[0].implementation

    def find(self, name: str) -> Any | None:
        records = self._services.get(name) or []
        return records[0].implementation if records else None

    def all(self, name: str) -> tuple[Any, ...]:
        return tuple(record.implementation for record in self._services.get(name) or ())

    def owners(self, name: str) -> tuple[str, ...]:
        return tuple(record.plugin_id for record in self._services.get(name) or ())

    def add_cleanup(self, plugin_id: str, callback: Callable[[], None]) -> None:
        self._cleanups.append((plugin_id, callback))

    def run_cleanups(self, *, plugin_id: str | None = None) -> list[str]:
        """Run registered cleanups in reverse. Returns error messages, never raises."""
        errors: list[str] = []
        remaining: list[tuple[str, Callable[[], None]]] = []
        for owner, callback in reversed(self._cleanups):
            if plugin_id is not None and owner != plugin_id:
                remaining.append((owner, callback))
                continue
            try:
                callback()
            except Exception as exc:
                errors.append(f"{owner}: {exc}")
        if plugin_id is None:
            self._cleanups.clear()
        else:
            self._cleanups = remaining
        if plugin_id is None:
            self._services.clear()
        else:
            for name, records in list(self._services.items()):
                kept = [record for record in records if record.plugin_id != plugin_id]
                if kept:
                    self._services[name] = kept
                else:
                    self._services.pop(name, None)
        return errors
