from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_host.errors import AuthorizationError

_FS_OPS = frozenset({"fs.read", "fs.write", "fs.list"})
_EXEC_OPS = frozenset({"exec"})


class WorkspacePolicy:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def authorize(self, plugin_id: str, operation: str, details: dict[str, Any]) -> None:
        if operation in _EXEC_OPS:
            raw = details.get("cwd") or details.get("path")
            self._must_be_inside(plugin_id, operation, raw)
            return
        if operation not in _FS_OPS:
            raise AuthorizationError(f"policy denied {operation!r} for plugin {plugin_id!r}")
        self._must_be_inside(plugin_id, operation, details.get("path"))

    def _must_be_inside(self, plugin_id: str, operation: str, raw: Any) -> None:
        if not raw:
            raise AuthorizationError(f"policy denied {operation!r} for plugin {plugin_id!r}: missing path")
        try:
            path = Path(str(raw)).resolve()
            path.relative_to(self.root)
        except (OSError, ValueError) as exc:
            raise AuthorizationError(
                f"policy denied {operation!r} outside workspace {self.root}: {raw}"
            ) from exc


def register(ctx) -> None:
    settings = ctx.settings()
    root = Path(str(settings.get("workspace") or ctx.data_dir() / "workspace"))
    root.mkdir(parents=True, exist_ok=True)
    ctx.register_service("policy.privilege", WorkspacePolicy(root))
