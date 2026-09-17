"""Discover plugin metadata without importing plugin implementations."""

from __future__ import annotations

import importlib.metadata
import json
import logging
from pathlib import Path
from typing import Any

from hermes_host.api import ENTRY_POINTS_GROUP
from hermes_host.config import HostConfig
from hermes_host.errors import PluginError
from hermes_host.metadata import PluginMetadata, iter_manifest_files, metadata_from_mapping, parse_metadata_file

logger = logging.getLogger("hermes_host.discovery")


def discover_metadata(config: HostConfig) -> list[PluginMetadata]:
    """Return metadata for every visible plugin. Does not import plugin modules."""
    found: list[PluginMetadata] = []
    for path in config.search_paths:
        found.extend(_scan_directory(path, source="search_path"))
    user_dir = config.home / "plugins"
    if user_dir.is_dir():
        found.extend(_scan_directory(user_dir, source="user"))
    if config.include_entry_points:
        found.extend(_scan_entry_points())
    return found


def _scan_directory(root: Path, *, source: str) -> list[PluginMetadata]:
    results: list[PluginMetadata] = []
    if not root.is_dir():
        return results
    try:
        children = sorted(root.iterdir())
    except OSError as exc:
        logger.warning("cannot list plugin directory %s: %s", root, exc)
        return results
    for child in children:
        try:
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
        except OSError as exc:
            logger.warning("skipping unreadable path %s: %s", child, exc)
            continue
        manifests = iter_manifest_files(child)
        if not manifests:
            continue
        try:
            results.append(parse_metadata_file(manifests[0], source=source))
        except PluginError as exc:
            logger.warning("%s", exc)
    return results


def _scan_entry_points() -> list[PluginMetadata]:
    results: list[PluginMetadata] = []
    try:
        eps = importlib.metadata.entry_points()
        group = list(eps.select(group=ENTRY_POINTS_GROUP)) if hasattr(eps, "select") else [
            ep for ep in eps if getattr(ep, "group", None) == ENTRY_POINTS_GROUP
        ]
    except Exception as exc:
        logger.debug("entry-point scan failed: %s", exc)
        return results
    for ep in group:
        try:
            results.append(_metadata_from_entry_point(ep))
        except PluginError as exc:
            logger.warning("%s", exc)
        except Exception as exc:
            logger.warning("entry-point plugin %s skipped: %s", getattr(ep, "name", "?"), exc)
    return results


def _metadata_from_entry_point(ep: Any) -> PluginMetadata:
    """Read plugin.json from the distribution. Never import the plugin module."""
    dist = getattr(ep, "dist", None)
    value = str(getattr(ep, "value", "") or "").strip()
    origin = f"entry-point:{getattr(ep, 'name', '?')}"
    data = None
    metadata_path = ""
    if dist is not None and value:
        data, metadata_path = _read_dist_file(dist, value)
    if data is None:
        raise PluginError(
            f"{origin} must point at a plugin.json packaged in the distribution, not a Python object"
        )
    return metadata_from_mapping(
        data, source="entrypoint", origin=origin, metadata_path=metadata_path
    )


def _read_dist_file(dist: Any, relative: str) -> tuple[dict | None, str]:
    relative = relative.replace("\\", "/").lstrip("/")
    files = getattr(dist, "files", None) or []
    match = None
    for loc in files:
        name = str(loc).replace("\\", "/")
        if name == relative or name.endswith("/" + relative) or name.endswith(relative):
            match = loc
            break
    if match is None:
        # Fallback: locate package dir next to the dist and read the file.
        locate = getattr(dist, "locate_file", None)
        if locate is None:
            return None, ""
        try:
            path = Path(locate(relative))
            text = path.read_text(encoding="utf-8-sig")
            payload = json.loads(text) if path.suffix.lower() == ".json" else None
            if payload is None:
                import yaml
                payload = yaml.safe_load(text)
            return (payload if isinstance(payload, dict) else None), str(path)
        except Exception:
            return None, ""
    try:
        raw = match.read_text(encoding="utf-8-sig") if hasattr(match, "read_text") else Path(
            dist.locate_file(match)
        ).read_text(encoding="utf-8-sig")
        path_str = str(dist.locate_file(match)) if hasattr(dist, "locate_file") else relative
        if relative.endswith((".yaml", ".yml")):
            import yaml
            payload = yaml.safe_load(raw)
        else:
            payload = json.loads(raw)
        return (payload if isinstance(payload, dict) else None), path_str
    except Exception:
        return None, ""
