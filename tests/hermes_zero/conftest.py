"""Hermes Zero kernel tests use a temp host home, never ~/.hermes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOST_SRC = ROOT / "packages" / "hermes-host" / "src"
SDK_SRC = ROOT / "packages" / "hermes-agent-sdk" / "src"
for path in (HOST_SRC, SDK_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture
def host_home(tmp_path: Path) -> Path:
    home = tmp_path / "host-home"
    home.mkdir()
    return home
