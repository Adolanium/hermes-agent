from __future__ import annotations

import json
from pathlib import Path


def write_plugin(
    root: Path,
    plugin_id: str,
    register_src: str,
    *,
    provides=None,
    requires=None,
    depends=None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    directory = root / plugin_id.replace(".", "_")
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": plugin_id,
        "version": "1.0.0",
        "host_api": 1,
        "name": plugin_id,
        "entry": "./plugin.py:register",
        "provides": provides or [],
        "requires": requires or [],
        "depends": depends or [],
    }
    (directory / "plugin.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (directory / "plugin.py").write_text(register_src, encoding="utf-8")
    for name, body in (extra_files or {}).items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return directory
