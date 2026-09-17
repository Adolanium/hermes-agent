"""Host CLI commands registered by plugins. Builtins stay in hermes_host.cli."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from hermes_host.errors import PluginError

BUILTIN_COMMANDS = frozenset({"status", "init", "plugins", "start", "run"})

Handler = Callable[[list[str]], int]


@dataclass(frozen=True)
class Command:
    name: str
    plugin_id: str
    handler: Handler
    help: str = ""


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, name: str, handler: Handler, *, plugin_id: str, help: str = "") -> None:
        clean = str(name or "").strip()
        if not clean or "/" in clean or " " in clean:
            raise PluginError(f"plugin {plugin_id!r} registered an invalid command name {name!r}")
        if clean in self._commands:
            owner = self._commands[clean].plugin_id
            raise PluginError(f"command {clean!r} is already registered by {owner!r}")
        if not callable(handler):
            raise PluginError(f"plugin {plugin_id!r} command {clean!r} handler is not callable")
        self._commands[clean] = Command(name=clean, plugin_id=plugin_id, handler=handler, help=help)

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._commands))

    def drop_plugin(self, plugin_id: str) -> None:
        for name, command in list(self._commands.items()):
            if command.plugin_id == plugin_id:
                del self._commands[name]
