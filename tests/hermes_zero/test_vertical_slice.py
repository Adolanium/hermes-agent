from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hermes_agent_sdk.runtime import TurnRequest
from hermes_host import Host, HostConfig

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SRC_DIRS = [
    ROOT / "packages" / "plugins" / "persistence" / "src",
    ROOT / "packages" / "plugins" / "tools-core" / "src",
    ROOT / "packages" / "plugins" / "openai-compat" / "src",
    ROOT / "packages" / "plugins" / "agent-runtime" / "src",
    ROOT / "packages" / "plugins" / "cli-stdio" / "src",
]
MINIMAL = [
    "hermes.persistence",
    "hermes.tools.core",
    "hermes.provider.openai-compat",
    "hermes.agent.runtime",
    "hermes.interface.stdio",
]


def _ensure_plugin_imports() -> None:
    for path in PLUGIN_SRC_DIRS:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def _start_provider(scripted=True):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            messages = body.get("messages") or []
            has_tool = any(item.get("role") == "tool" for item in messages)
            if scripted and not has_tool:
                user = next((item.get("content") for item in reversed(messages) if item.get("role") == "user"), "")
                payload = {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_echo",
                                        "type": "function",
                                        "function": {
                                            "name": "echo",
                                            "arguments": json.dumps({"text": user}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            elif scripted:
                tool_text = next(
                    item.get("content") for item in reversed(messages) if item.get("role") == "tool"
                )
                payload = {"choices": [{"message": {"role": "assistant", "content": f"echoed:{tool_text}"}}]}
            else:
                payload = {"choices": [{"message": {"role": "assistant", "content": "plain"}}]}
            blob = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def log_message(self, format, *args):  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _host(home: Path, enabled, *, base_url: str, extra_paths=(), extra_enabled=(), selection=None):
    _ensure_plugin_imports()
    search = tuple(PLUGIN_SRC_DIRS) + tuple(extra_paths)
    return Host(
        HostConfig(
            home=home,
            enabled=tuple(enabled) + tuple(extra_enabled),
            search_paths=search,
            include_entry_points=False,
            service_selection=selection or {},
            plugin_settings={
                "hermes.provider.openai-compat": {
                    "base_url": base_url,
                    "api_key": "test",
                    "model": "fixture",
                }
            },
        )
    )


def test_minimal_composition_runs_tool_then_text(host_home):
    server = _start_provider(scripted=True)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        host = _host(host_home, MINIMAL, base_url=base_url)
        host.start()
        try:
            result = host.get_service("interface.stdio").run_text("hello", session_id="s1")
            assert result.error is None
            assert result.text == "echoed:hello"
            stored = host.get_service("persistence.sessions").load("s1")
            assert stored[-1].role == "assistant"
            assert any(message.role == "tool" for message in stored)
        finally:
            host.stop()
    finally:
        server.shutdown()


def test_alternate_runtime_replaces_first_party_loop(host_home):
    examples = ROOT / "docs" / "hermes-zero" / "examples"
    host = _host(
        host_home,
        ("hermes.persistence", "hermes.tools.core", "hermes.provider.openai-compat"),
        base_url="http://127.0.0.1:9/v1",
        extra_paths=(examples,),
        extra_enabled=("example.alternate-runtime",),
        selection={"agent.runtime": "example.alternate-runtime"},
    )
    host.start()
    try:
        runtime = host.get_service("agent.runtime")
        result = runtime.run(TurnRequest(text="ping"))
        assert result.text == "alternate:ping"
    finally:
        host.stop()


def test_external_tool_plugin_registers_on_public_registry(host_home):
    server = _start_provider(scripted=False)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        host = _host(
            host_home,
            MINIMAL,
            base_url=base_url,
            extra_paths=(ROOT / "docs" / "hermes-zero" / "examples",),
            extra_enabled=("example.external-echo",),
        )
        host.start()
        try:
            registry = host.get_service("tool.registry")
            names = [schema["function"]["name"] for schema in registry.schemas()]
            assert "echo" in names
            assert "shout" in names
            from hermes_agent_sdk.messages import ToolCall
            shouted = registry.invoke(ToolCall(id="1", name="shout", arguments={"text": "hi"}))
            assert shouted.content == "HI"
        finally:
            host.stop()
    finally:
        server.shutdown()


def test_removing_external_plugin_leaves_core_tools(host_home):
    server = _start_provider(scripted=False)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        host = _host(host_home, MINIMAL, base_url=base_url)
        host.start()
        try:
            names = [schema["function"]["name"] for schema in host.get_service("tool.registry").schemas()]
            assert names == ["echo"]
        finally:
            host.stop()
    finally:
        server.shutdown()
