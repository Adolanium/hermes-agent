"""Kernel CLI. Application commands are registered by plugins, not by this module."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from hermes_host import HOST_API_VERSION
from hermes_host.config import HostConfig, load_host_config, write_host_config
from hermes_host.errors import CapabilityError, CompositionError, HostError, PluginError
from hermes_host.host import Host


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        code = exc.code
        if code in (0, None):
            return 0
        return code if isinstance(code, int) else 2
    if not getattr(args, "home", None):
        print("error: --home is required (this host will not use ~/.hermes)", file=sys.stderr)
        return 2
    home = Path(args.home).expanduser()
    try:
        return args.handler(args, home)
    except (HostError, CapabilityError, CompositionError, PluginError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-host",
        description="Hermes Zero plugin host. Application features are plugins.",
    )
    parser.add_argument("--home", required=True, help="Host data directory (not the user's ~/.hermes)")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show host status without starting plugins")
    status.set_defaults(handler=_cmd_status)

    init = sub.add_parser("init", help="Write a default host.toml with no plugins enabled")
    init.set_defaults(handler=_cmd_init)

    plist = sub.add_parser("plugins", help="Plugin metadata operations")
    psub = plist.add_subparsers(dest="plugins_command", required=True)
    listed = psub.add_parser("list", help="List discovered plugin metadata")
    listed.set_defaults(handler=_cmd_plugins_list)
    enable = psub.add_parser("enable", help="Add a plugin id to the enabled list")
    enable.add_argument("plugin_id")
    enable.set_defaults(handler=_cmd_enable)
    disable = psub.add_parser("disable", help="Remove a plugin id from the enabled list")
    disable.add_argument("plugin_id")
    disable.set_defaults(handler=_cmd_disable)

    start = sub.add_parser("start", help="Start the enabled composition and stop immediately (lifecycle check)")
    start.set_defaults(handler=_cmd_start)

    run = sub.add_parser("run", help="Start the composition and idle until SIGINT")
    run.set_defaults(handler=_cmd_run)
    return parser


def _load(home: Path) -> Host:
    home.mkdir(parents=True, exist_ok=True)
    config = load_host_config(home)
    return Host(config)


def _cmd_status(_args: argparse.Namespace, home: Path) -> int:
    host = _load(home)
    discovered = host.discover()
    composition = resolve_safe(host)
    payload = {
        "host_api": HOST_API_VERSION,
        "home": str(host.config.home),
        "running": host.running,
        "enabled": list(host.config.enabled),
        "discovered": [
            {"id": item.id, "version": item.version, "source": item.source, "origin": item.origin}
            for item in discovered
        ],
        "selected": [item.id for item in composition.selected] if composition else [],
        "error": None if composition is not None else "composition is empty or invalid",
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_init(_args: argparse.Namespace, home: Path) -> int:
    home.mkdir(parents=True, exist_ok=True)
    path = write_host_config(HostConfig(home=home.resolve()))
    print(f"wrote {path}")
    return 0


def _cmd_plugins_list(_args: argparse.Namespace, home: Path) -> int:
    host = _load(home)
    for item in host.discover():
        state = "enabled" if item.id in host.config.enabled else "disabled"
        print(f"{item.id:40} {item.version:10} {state:10} {item.source}")
    return 0


def _cmd_enable(args: argparse.Namespace, home: Path) -> int:
    config = load_host_config(home)
    enabled = list(config.enabled)
    if args.plugin_id not in enabled:
        enabled.append(args.plugin_id)
    write_host_config(
        HostConfig(
            home=config.home,
            enabled=tuple(enabled),
            disabled=tuple(x for x in config.disabled if x != args.plugin_id),
            search_paths=config.search_paths,
            service_selection=config.service_selection,
            include_entry_points=config.include_entry_points,
            plugin_settings=config.plugin_settings,
        )
    )
    print(f"enabled {args.plugin_id}")
    return 0


def _cmd_disable(args: argparse.Namespace, home: Path) -> int:
    config = load_host_config(home)
    write_host_config(
        HostConfig(
            home=config.home,
            enabled=tuple(x for x in config.enabled if x != args.plugin_id),
            disabled=tuple(dict.fromkeys([*config.disabled, args.plugin_id])),
            search_paths=config.search_paths,
            service_selection=config.service_selection,
            include_entry_points=config.include_entry_points,
            plugin_settings=config.plugin_settings,
        )
    )
    print(f"disabled {args.plugin_id}")
    return 0


def _cmd_start(_args: argparse.Namespace, home: Path) -> int:
    host = _load(home)
    composition = host.start()
    try:
        print(json.dumps({"started": [item.id for item in composition.selected]}, indent=2))
    finally:
        host.stop()
    return 0


def _cmd_run(_args: argparse.Namespace, home: Path) -> int:
    host = _load(home)
    host.start()
    try:
        print(f"host running with {len(host.config.enabled)} plugin(s). Ctrl-C to stop.", file=sys.stderr)
        host._cancelled.wait()
    except KeyboardInterrupt:
        pass
    finally:
        host.stop()
    return 0


def resolve_safe(host: Host):
    try:
        return host.resolve()
    except HostError:
        return None
