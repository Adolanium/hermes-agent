from __future__ import annotations

import sys
from pathlib import Path

from hermes_agent_sdk.messages import ToolCall
from hermes_host import Host, HostConfig

ROOT = Path(__file__).resolve().parents[2]
SRC = [
    ROOT / "packages" / "plugins" / "tools-core" / "src",
    ROOT / "packages" / "plugins" / "policy-workspace" / "src",
    ROOT / "packages" / "plugins" / "tools-fs" / "src",
]


def test_fs_tools_fail_closed_outside_workspace_and_work_inside(host_home, tmp_path):
    for path in SRC:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    inside = workspace / "note.txt"
    host = Host(
        HostConfig(
            home=host_home,
            enabled=("hermes.tools.core", "hermes.policy.workspace", "hermes.tools.fs"),
            search_paths=tuple(SRC),
            include_entry_points=False,
            plugin_settings={"hermes.policy.workspace": {"workspace": str(workspace)}},
        )
    )
    host.start()
    try:
        registry = host.get_service("tool.registry")
        denied = registry.invoke(ToolCall(id="1", name="read_file", arguments={"path": str(tmp_path / "secret.txt")}))
        assert denied.is_error
        written = registry.invoke(
            ToolCall(id="2", name="write_file", arguments={"path": str(inside), "content": "ok"})
        )
        assert not written.is_error
        read = registry.invoke(ToolCall(id="3", name="read_file", arguments={"path": str(inside)}))
        assert read.content == "ok"
    finally:
        host.stop()
