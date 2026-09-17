"""Host configuration. Plugin-specific settings live in each plugin's own mapping."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from hermes_host.errors import HostError

_CONFIG_NAMES = ("host.toml", "host.json", "host.yaml", "host.yml")


@dataclass(frozen=True)
class HostConfig:
    """Instance-scoped host configuration.

    ``home`` is the host data directory. It is never ``~/.hermes`` by default:
    this fork must not touch the user's live Hermes profile.
    """

    home: Path
    enabled: tuple[str, ...] = ()
    disabled: tuple[str, ...] = ()
    search_paths: tuple[Path, ...] = ()
    service_selection: Mapping[str, str] = field(default_factory=dict)
    include_entry_points: bool = True
    plugin_settings: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @property
    def plugins_data_dir(self) -> Path:
        return self.home / "plugin-data"

    @property
    def config_path(self) -> Path:
        for name in _CONFIG_NAMES:
            candidate = self.home / name
            if candidate.is_file():
                return candidate
        return self.home / "host.toml"


def load_host_config(home: Path, *, overrides: Mapping[str, Any] | None = None) -> HostConfig:
    """Load config from ``home`` plus optional overlay mapping (CLI flags)."""
    home = Path(home).expanduser().resolve()
    raw: dict[str, Any] = {}
    for name in _CONFIG_NAMES:
        path = home / name
        if path.is_file():
            raw = _read_mapping(path)
            break
    if overrides:
        raw = _deep_merge(raw, dict(overrides))
    plugins = raw.get("plugins") if isinstance(raw.get("plugins"), dict) else {}
    services = raw.get("services") if isinstance(raw.get("services"), dict) else {}
    settings = plugins.get("settings") if isinstance(plugins.get("settings"), dict) else {}
    search = []
    for item in plugins.get("search_paths") or []:
        search.append((home / str(item)).resolve() if not Path(str(item)).is_absolute() else Path(str(item)))
    enabled = tuple(_string_list(plugins.get("enabled")))
    disabled = tuple(_string_list(plugins.get("disabled")))
    selection = {str(k): str(v) for k, v in services.items() if v is not None}
    include_eps = bool(plugins.get("include_entry_points", True))
    plugin_settings = {
        str(pid): dict(body) for pid, body in settings.items() if isinstance(body, dict)
    }
    return HostConfig(
        home=home,
        enabled=enabled,
        disabled=disabled,
        search_paths=tuple(search),
        service_selection=selection,
        include_entry_points=include_eps,
        plugin_settings=plugin_settings,
    )


def write_host_config(config: HostConfig) -> Path:
    """Write TOML config. Host-owned; plugins never write this file themselves."""
    config.home.mkdir(parents=True, exist_ok=True)
    path = config.home / "host.toml"
    lines = [
        "# Hermes Zero host configuration. Application plugins are opt-in.",
        "[host]",
        f'home = {_toml_str(str(config.home))}',
        "",
        "[plugins]",
        f"enabled = {_toml_array(config.enabled)}",
        f"disabled = {_toml_array(config.disabled)}",
        f"search_paths = {_toml_array(str(p) for p in config.search_paths)}",
        f"include_entry_points = {'true' if config.include_entry_points else 'false'}",
        "",
        "[services]",
    ]
    if config.service_selection:
        for key, value in sorted(config.service_selection.items()):
            lines.append(f"{_toml_str(key)} = {_toml_str(value)}")
    else:
        lines.append("# \"model.provider\" = \"hermes.provider.openai-compat\"")
    lines.append("")
    if config.plugin_settings:
        for plugin_id, body in sorted(config.plugin_settings.items()):
            lines.append(f"[plugins.settings.{_toml_str(plugin_id)}]")
            if isinstance(body, dict):
                for key, value in body.items():
                    lines.append(f"{key} = {_toml_encode(value)}")
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _read_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    if suffix == ".toml":
        import tomllib
        data = tomllib.loads(text)
    elif suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        import yaml
        data = yaml.safe_load(text)
    else:
        raise HostError(f"unsupported host config format: {path}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HostError(f"host config must be a mapping: {path}")
    return data


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values) -> str:
    return "[" + ", ".join(_toml_str(str(v)) for v in values) + "]"


def _toml_encode(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return _toml_array(value)
    return _toml_str(str(value))
