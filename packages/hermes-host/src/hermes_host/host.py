"""Host instance: discover, resolve, start, stop. No application behavior."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Iterable

from hermes_host.config import HostConfig
from hermes_host.context import HostContext
from hermes_host.discovery import discover_metadata
from hermes_host.errors import CapabilityError, CompositionError, PluginError
from hermes_host.commands import CommandRegistry
from hermes_host.events import EventBus
from hermes_host.loader import load_register
from hermes_host.metadata import PluginMetadata
from hermes_host.policy import FailClosedPolicy, PrivilegePolicy, resolve_policy
from hermes_host.registry import ServiceRegistry
from hermes_host.resolve import Composition, resolve_composition

logger = logging.getLogger("hermes_host")


class Host:
    """One composition. Create a second instance to prove isolation."""

    def __init__(self, config: HostConfig) -> None:
        self.config = config
        self.id = uuid.uuid4().hex
        self._composition: Composition | None = None
        self._registry = ServiceRegistry()
        self._events = EventBus()
        self.commands = CommandRegistry()
        self._cancelled = threading.Event()
        self._started: list[str] = []
        self._contexts: dict[str, HostContext] = {}
        self._running = False
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        return self._running

    def discover(self) -> list[PluginMetadata]:
        return discover_metadata(self.config)

    def resolve(self) -> Composition:
        composition = resolve_composition(self.discover(), self.config)
        self._composition = composition
        return composition

    def start(self) -> Composition:
        """Import and start only the enabled composition. Rolls back on failure."""
        with self._lock:
            if self._running:
                raise CompositionError("host is already running")
            self._cancelled.clear()
            composition = self.resolve()
            started: list[str] = []
            try:
                for meta in composition.selected:
                    self._activate(meta, composition)
                    started.append(meta.id)
                self._assert_required_services(composition)
                for plugin_id in started:
                    for hook in self._contexts[plugin_id].start_hooks():
                        hook()
            except Exception:
                self._rollback(started)
                raise
            self._started = started
            self._running = True
            self._events.emit("host.started", {"host_id": self.id, "plugins": list(started)})
            return composition

    def stop(self) -> None:
        with self._lock:
            self._cancelled.set()
            errors = self._registry.run_cleanups()
            for plugin_id in reversed(self._started):
                self._events.drop_plugin(plugin_id)
                self.commands.drop_plugin(plugin_id)
            self._contexts.clear()
            self._started = []
            self._running = False
            self._events.emit("host.stopped", {"host_id": self.id, "cleanup_errors": errors})
            for message in errors:
                logger.warning("plugin cleanup error: %s", message)

    def cancel(self) -> None:
        self._cancelled.set()
        self._events.emit("host.cancelled", {"host_id": self.id})

    def get_service(self, name: str) -> Any:
        if not self._running:
            raise CapabilityError(f"host is not running; service {name!r} is unavailable")
        return self._registry.get(name)

    def find_service(self, name: str) -> Any | None:
        if not self._running:
            return None
        return self._registry.find(name)

    def require_capability(self, service_name: str, *, what: str) -> Any:
        impl = self.find_service(service_name)
        if impl is None:
            raise CapabilityError(
                f"{what} is not available because no plugin provides {service_name!r}"
            )
        return impl

    def _activate(self, meta: PluginMetadata, composition: Composition) -> None:
        register = load_register(meta, host_id=self.id)
        data_dir = self.config.plugins_data_dir / meta.id
        policy: PrivilegePolicy = resolve_policy(self._registry.find("policy.privilege"))
        ctx = HostContext(
            host_id=self.id,
            metadata=meta,
            data_dir=data_dir,
            settings=self.config.plugin_settings.get(meta.id, {}),
            registry=self._registry,
            events=self._events,
            commands=self.commands,
            cancelled=self._cancelled,
            policy=policy,
            allowed_service_owners=composition.service_owners,
            log=logging.getLogger(f"hermes_host.plugin.{meta.id}"),
        )
        try:
            register(ctx)
        except PluginError:
            raise
        except Exception as exc:
            raise PluginError(f"plugin {meta.id!r} register() failed: {exc}") from exc
        self._contexts[meta.id] = ctx
        # A policy plugin may have just registered. Subsequent plugins see it.
        if ctx.find_service("policy.privilege") is not None:
            ctx._policy = resolve_policy(ctx.find_service("policy.privilege"))

    def _assert_required_services(self, composition: Composition) -> None:
        for meta in composition.selected:
            for spec in meta.requires:
                if spec.optional:
                    continue
                if self._registry.find(spec.name) is None:
                    raise CompositionError(
                        f"plugin {meta.id!r} requires service {spec.name!r}, which no enabled plugin provides"
                    )

    def _rollback(self, started: Iterable[str]) -> None:
        plugin_ids = list(started)
        for plugin_id in reversed(plugin_ids):
            errors = self._registry.run_cleanups(plugin_id=plugin_id)
            self._events.drop_plugin(plugin_id)
            self.commands.drop_plugin(plugin_id)
            self._contexts.pop(plugin_id, None)
            for message in errors:
                logger.warning("rollback cleanup error: %s", message)
        self._started = []
        self._running = False
