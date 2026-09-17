"""Plugin metadata. Parsed from JSON/YAML files. Never imports plugin code."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from hermes_host.api import HOST_API_VERSION
from hermes_host.errors import PluginError

_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_MANIFEST_NAMES = ("plugin.json", "plugin.yaml", "plugin.yml")


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    unique: bool = True
    optional: bool = False


@dataclass(frozen=True)
class PluginDependency:
    plugin_id: str
    version: str | None = None


@dataclass(frozen=True)
class PluginMetadata:
    id: str
    version: str
    host_api: int
    entry: str
    name: str = ""
    description: str = ""
    provides: tuple[ServiceSpec, ...] = ()
    requires: tuple[ServiceSpec, ...] = ()
    depends: tuple[PluginDependency, ...] = ()
    source: str = "directory"
    origin: str = ""
    metadata_path: str = ""

    @property
    def directory(self) -> Path | None:
        if not self.metadata_path:
            return None
        return Path(self.metadata_path).parent


def parse_metadata_file(path: Path, *, source: str = "directory") -> PluginMetadata:
    """Read one manifest file. Raises PluginError on malformed input."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise PluginError(f"cannot read plugin metadata {path}: {exc}") from exc
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            data = json.loads(text)
        elif suffix in {".yaml", ".yml"}:
            import yaml
            data = yaml.safe_load(text)
        else:
            raise PluginError(f"unsupported plugin metadata format: {path}")
    except PluginError:
        raise
    except Exception as exc:
        raise PluginError(f"plugin metadata is not valid in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PluginError(f"plugin metadata must be a mapping: {path}")
    return metadata_from_mapping(data, source=source, origin=str(path), metadata_path=str(path))


def metadata_from_mapping(
    data: Mapping[str, Any],
    *,
    source: str,
    origin: str,
    metadata_path: str = "",
) -> PluginMetadata:
    plugin_id = str(data.get("id") or "").strip()
    if not plugin_id or not _ID_RE.match(plugin_id):
        raise PluginError(f"plugin id {plugin_id!r} is invalid in {origin}")
    version = str(data.get("version") or "").strip()
    if not version:
        raise PluginError(f"plugin {plugin_id!r} is missing version in {origin}")
    try:
        host_api = int(data.get("host_api"))
    except (TypeError, ValueError) as exc:
        raise PluginError(f"plugin {plugin_id!r} host_api must be an integer in {origin}") from exc
    if host_api != HOST_API_VERSION:
        raise PluginError(
            f"plugin {plugin_id!r} declares host_api={host_api}, host supports {HOST_API_VERSION}"
        )
    entry = str(data.get("entry") or "").strip()
    if not entry or ":" not in entry:
        raise PluginError(
            f"plugin {plugin_id!r} entry must be 'module:attr' or './file.py:attr' in {origin}"
        )
    provides = tuple(_service_list(data.get("provides"), plugin_id, origin, default_unique=True))
    requires = tuple(_service_list(data.get("requires"), plugin_id, origin, default_unique=True))
    depends = tuple(_depends_list(data.get("depends"), plugin_id, origin))
    return PluginMetadata(
        id=plugin_id,
        version=version,
        host_api=host_api,
        entry=entry,
        name=str(data.get("name") or plugin_id),
        description=str(data.get("description") or ""),
        provides=provides,
        requires=requires,
        depends=depends,
        source=source,
        origin=origin,
        metadata_path=metadata_path,
    )


def iter_manifest_files(directory: Path) -> list[Path]:
    found = []
    for name in _MANIFEST_NAMES:
        candidate = directory / name
        if candidate.is_file():
            found.append(candidate)
            break
    return found


def _service_list(raw: Any, plugin_id: str, origin: str, *, default_unique: bool) -> list[ServiceSpec]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PluginError(f"plugin {plugin_id!r} provides/requires must be a list in {origin}")
    out: list[ServiceSpec] = []
    for item in raw:
        if isinstance(item, str):
            out.append(ServiceSpec(name=item, unique=default_unique))
            continue
        if not isinstance(item, Mapping) or not item.get("service"):
            raise PluginError(f"plugin {plugin_id!r} has a malformed service spec in {origin}")
        out.append(
            ServiceSpec(
                name=str(item["service"]),
                unique=bool(item.get("unique", default_unique)),
                optional=bool(item.get("optional", False)),
            )
        )
    return out


def _depends_list(raw: Any, plugin_id: str, origin: str) -> list[PluginDependency]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PluginError(f"plugin {plugin_id!r} depends must be a list in {origin}")
    out: list[PluginDependency] = []
    for item in raw:
        if isinstance(item, str):
            out.append(PluginDependency(plugin_id=item))
            continue
        if not isinstance(item, Mapping) or not item.get("plugin"):
            raise PluginError(f"plugin {plugin_id!r} has a malformed depends entry in {origin}")
        version = item.get("version")
        out.append(
            PluginDependency(
                plugin_id=str(item["plugin"]),
                version=str(version) if version is not None else None,
            )
        )
    return out
