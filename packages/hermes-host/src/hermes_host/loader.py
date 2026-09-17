"""Import plugin implementations only after they are selected."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable

from hermes_host.errors import PluginError
from hermes_host.metadata import PluginMetadata

logger = logging.getLogger("hermes_host.loader")


def load_register(meta: PluginMetadata, *, host_id: str) -> Callable[..., Any]:
    """Import the selected plugin and return its register callable."""
    module_ref, _, attr = meta.entry.partition(":")
    attr = attr or "register"
    module_ref = module_ref.strip()
    if not module_ref or not attr:
        raise PluginError(f"plugin {meta.id!r} has an unusable entry {meta.entry!r}")
    if _is_file_entry(module_ref):
        module = _load_from_file(meta, module_ref, host_id=host_id)
    else:
        try:
            module = importlib.import_module(module_ref)
        except Exception as exc:
            raise PluginError(f"plugin {meta.id!r} could not be imported ({module_ref}): {exc}") from exc
    try:
        register = getattr(module, attr)
    except AttributeError as exc:
        raise PluginError(f"plugin {meta.id!r} has no attribute {attr!r} on {module_ref}") from exc
    if not callable(register):
        raise PluginError(f"plugin {meta.id!r} entry {meta.entry!r} is not callable")
    return register


def _is_file_entry(module_ref: str) -> bool:
    return module_ref.startswith("./") or module_ref.endswith(".py") or "/" in module_ref or "\\" in module_ref


def _load_from_file(meta: PluginMetadata, module_ref: str, *, host_id: str) -> Any:
    directory = meta.directory
    if directory is None:
        raise PluginError(f"plugin {meta.id!r} file entry requires a metadata path")
    path = (directory / module_ref).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError as exc:
        raise PluginError(f"plugin {meta.id!r} entry escapes its directory: {path}") from exc
    if not path.is_file():
        raise PluginError(f"plugin {meta.id!r} entry file does not exist: {path}")
    module_name = f"hermes_host._ext.{_safe_id(host_id)}_{_safe_id(meta.id)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginError(f"plugin {meta.id!r} could not build a module spec from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise PluginError(f"plugin {meta.id!r} failed while importing {path}: {exc}") from exc
    return module


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)
