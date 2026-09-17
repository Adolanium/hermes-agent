"""CLI-only Hermes Agent. Commands run and exit. No TUI, desktop, or gateway."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from hermes_zero import PROGRAMMING_PLUGINS
from hermes_zero.paths import default_home, ensure_dev_imports, plugin_search_paths

HELP = """Hermes Zero — CLI agent only.

TUI, desktop, dashboard, and messaging gateways are not part of this build.
Commands run and then exit. There is no waiting prompt.

Usage:
  hermes query <text>                 Run one agent turn (files + terminal tools)
  hermes tools                        List tools
  hermes read <path>                  Read a workspace file
  hermes write <path> <content...>    Write a workspace file
  hermes terminal --cwd <dir> <argv>  Run a command in the workspace
  hermes status                       Plugin host status
  hermes plugins list|enable|disable

--home defaults to ./.hermes-zero (not ~/.hermes).
"""

STRIPPED = """Hermes Zero does not include the TUI, desktop app, dashboard, or
messaging gateway. This is a CLI-only agent.

Use:  hermes query <text>
"""

REMOVED_COMMANDS = frozenset({
    "tui", "desktop", "gui", "gateway", "dashboard", "serve", "acp", "cron",
    "kanban", "webhooks", "webhook",
})
HOST_COMMANDS = frozenset({
    "tools", "read", "write", "terminal", "status", "plugins", "init", "start",
})


def main(argv: Sequence[str] | None = None) -> int:
    ensure_dev_imports()
    raw = list(argv) if argv is not None else sys.argv[1:]
    if not raw or raw[0] in {"-h", "--help", "help"}:
        print(HELP)
        return 0
    if "--tui" in raw or raw[0] in REMOVED_COMMANDS:
        print(STRIPPED, file=sys.stderr)
        return 2

    if raw[0] in {"query", "-q", "--query"}:
        return _agent_query(" ".join(raw[1:]))

    if raw[0] in HOST_COMMANDS:
        return _host_main(raw)

    # `hermes fix the tests` — one agent turn, then exit.
    return _agent_query(" ".join(raw))


def _agent_query(prompt: str) -> int:
    prompt = prompt.strip()
    if not prompt:
        print("usage: hermes query <text>", file=sys.stderr)
        return 2
    try:
        from hermes_cli.oneshot import run_oneshot
    except ImportError:
        return _host_main(["query", prompt])
    return int(run_oneshot(prompt) or 0)


def _host_main(raw: list[str]) -> int:
    from hermes_host.cli import main as host_main
    from hermes_host.config import HostConfig, write_host_config

    if "--home" not in raw and not any(item.startswith("--home=") for item in raw):
        raw = ["--home", str(default_home()), *raw]
    home = _home_from(raw)
    _ensure_programming_home(home, HostConfig, write_host_config)
    return host_main(raw)


def _ensure_programming_home(home: Path, HostConfig, write_host_config) -> None:
    home.mkdir(parents=True, exist_ok=True)
    if (home / "host.toml").is_file():
        return
    write_host_config(
        HostConfig(
            home=home.resolve(),
            enabled=PROGRAMMING_PLUGINS,
            search_paths=tuple(plugin_search_paths()),
            include_entry_points=True,
            service_selection={
                "persistence.sessions": "hermes.persistence.sqlite",
                "model.provider": "hermes.provider.openai-compat",
            },
            plugin_settings={
                "hermes.policy.workspace": {"workspace": str(Path.cwd().resolve())},
                "hermes.provider.openai-compat": {
                    "base_url": "",
                    "api_key": "",
                    "model": "default",
                },
            },
        )
    )


def _home_from(argv: Sequence[str]) -> Path:
    items = list(argv)
    for index, token in enumerate(items):
        if token == "--home" and index + 1 < len(items):
            return Path(items[index + 1]).expanduser()
        if token.startswith("--home="):
            return Path(token.split("=", 1)[1]).expanduser()
    return default_home()
