from __future__ import annotations

import sys
from pathlib import Path

from hermes_agent_sdk.messages import ToolCall
from hermes_host import Host, HostConfig

ROOT = Path(__file__).resolve().parents[2]
SRC = [
    ROOT / "packages" / "plugins" / "tools-core" / "src",
    ROOT / "packages" / "plugins" / "policy-workspace" / "src",
    ROOT / "packages" / "plugins" / "tools-terminal" / "src",
]


def test_terminal_runs_inside_workspace_and_denies_outside(host_home, tmp_path):
    for path in SRC:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    script = workspace / "hi.py"
    script.write_text("print('from-term')\n", encoding="utf-8")
    host = Host(
        HostConfig(
            home=host_home,
            enabled=("hermes.tools.core", "hermes.policy.workspace", "hermes.tools.terminal"),
            search_paths=tuple(SRC),
            include_entry_points=False,
            plugin_settings={"hermes.policy.workspace": {"workspace": str(workspace)}},
        )
    )
    host.start()
    try:
        registry = host.get_service("tool.registry")
        denied = registry.invoke(
            ToolCall(
                id="1",
                name="terminal",
                arguments={"command": f"{sys.executable} {script}", "cwd": str(tmp_path)},
            )
        )
        assert denied.is_error
        ok = registry.invoke(
            ToolCall(
                id="2",
                name="terminal",
                arguments={"command": f"{sys.executable} {script.name}", "cwd": str(workspace)},
            )
        )
        assert not ok.is_error
        assert "from-term" in ok.content
    finally:
        host.stop()
