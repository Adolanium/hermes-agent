from __future__ import annotations

import sys
from pathlib import Path

from hermes_agent_sdk.messages import Message
from hermes_host import Host, HostConfig

ROOT = Path(__file__).resolve().parents[2]
SRC = [
    ROOT / "packages" / "plugins" / "persistence" / "src",
    ROOT / "packages" / "plugins" / "persistence-sqlite" / "src",
]


def test_sqlite_store_replaces_json_via_service_selection(host_home):
    for path in SRC:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    host = Host(
        HostConfig(
            home=host_home,
            enabled=("hermes.persistence", "hermes.persistence.sqlite"),
            search_paths=tuple(SRC),
            include_entry_points=False,
            service_selection={"persistence.sessions": "hermes.persistence.sqlite"},
        )
    )
    host.start()
    try:
        store = host.get_service("persistence.sessions")
        store.save("s1", [Message(role="user", content="hi")])
        loaded = store.load("s1")
        assert loaded[0].content == "hi"
        assert (host.config.plugins_data_dir / "hermes.persistence.sqlite" / "sessions.sqlite").is_file()
        json_dir = host.config.plugins_data_dir / "hermes.persistence" / "sessions"
        assert not json_dir.exists() or not any(json_dir.glob("*.json"))
    finally:
        host.stop()
