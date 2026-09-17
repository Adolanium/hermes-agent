from __future__ import annotations

import sys
from pathlib import Path


def default_home() -> Path:
    """Project-local data dir. Never ~/.hermes."""
    return (Path.cwd() / ".hermes-zero").resolve()


def plugin_search_paths() -> list[Path]:
    """In-repo plugin src dirs for editable checkouts. Empty when installed as a wheel."""
    here = Path(__file__).resolve()
    # packages/hermes-zero/src/hermes_zero/paths.py -> packages/
    packages = here.parents[3] if len(here.parents) >= 4 else None
    if packages is None or packages.name != "packages":
        # .../site-packages/hermes_zero/paths.py
        return []
    plugins_root = packages / "plugins"
    if not plugins_root.is_dir():
        return []
    return sorted(
        src
        for child in plugins_root.iterdir()
        if child.is_dir() and (src := child / "src").is_dir()
    )


def ensure_dev_imports() -> None:
    """Put in-repo package src dirs on sys.path for a source checkout."""
    here = Path(__file__).resolve()
    if len(here.parents) < 4 or here.parents[3].name != "packages":
        return
    packages = here.parents[3]
    for src in (
        packages / "hermes-host" / "src",
        packages / "hermes-agent-sdk" / "src",
        packages / "hermes-zero" / "src",
        *plugin_search_paths(),
    ):
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
