"""Real launch paths load provider profiles and general plugins before use."""

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys

import httpx
import pytest

from hermes_cli.config import save_config
from tests.agui_adapter.test_modernization_probe import body, events
from tests.waiting import wait_until


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("launcher", ["main", "module", "console-function"])
def test_entry_points_use_configured_provider_and_discover_plugin_tools(peer, launcher):
    home = Path(os.environ["HERMES_HOME"])
    provider = home / "plugins/model-providers/agui-startup-provider"
    provider.mkdir(parents=True)
    (provider / "__init__.py").write_text(
        "from providers import register_provider\n"
        "from providers.base import ProviderProfile\n"
        "class ProbeProfile(ProviderProfile):\n"
        "    def build_api_kwargs_extras(self, **context):\n"
        "        return {'agui_provider_probe': 'profile-loaded'}, {}\n"
        "register_provider(ProbeProfile(\n"
        "    name='agui-startup-provider', env_vars=('AGUI_PROBE_API_KEY',),\n"
        f"    base_url='http://127.0.0.1:{peer.server_port}/v1',\n"
        "    api_mode='chat_completions', supports_model_listing=False))\n"
    )
    plugin = home / "plugins/agui-startup-plugin"
    plugin.mkdir()
    (plugin / "plugin.yaml").write_text("name: agui-startup-plugin\nversion: 0.1.0\n")
    (plugin / "__init__.py").write_text(
        "def register(ctx):\n"
        "    ctx.register_tool(name='agui_startup_echo', toolset='agui-startup-plugin',\n"
        "        schema={'name': 'agui_startup_echo', 'description': 'Local probe',\n"
        "            'parameters': {'type': 'object', 'properties': {}}},\n"
        "        handler=lambda args, **kwargs: 'PLUGIN_TOOL_EXECUTED', check_fn=lambda: True)\n"
    )
    (home / ".env").write_text("AGUI_PROBE_API_KEY=local-profile-secret-only\n")
    save_config(
        {
            "model": {"provider": "agui-startup-provider", "default": "gpt-4o"},
            "plugins": {"enabled": ["agui-startup-plugin"]},
            "agui": {"toolsets": ["agui-startup-plugin"]},
            "auxiliary": {"title_generation": {"enabled": False}},
        }
    )
    peer.tool_name = "agui_startup_echo"
    peer.tool_args = {}
    peer.request_headers = []
    prefixes = {
        "main": ["-m", "hermes_cli.main", "agui"],
        "module": ["-m", "agui_adapter"],
        # Exact function invoked by the installed console-script wrapper.
        "console-function": ["-c", "from agui_adapter.cli import main; main()"],
    }
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with subprocess.Popen(
        [
            sys.executable,
            *prefixes[launcher],
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=15
            ) as client:

                def ready():
                    assert process.poll() is None, (
                        "adapter exited during provider/plugin startup"
                    )
                    try:
                        return client.get("/health").status_code == 200
                    except httpx.TransportError:
                        return False

                wait_until(ready, timeout=20, what=f"{launcher} plugin-backed listener")
                result = events(client.post("/", json=body("startup-probe")))
                text = "".join(e.get("delta", "") for e in result)
                assert "PLUGIN_TOOL_EXECUTED" in text, text
                assert len(peer.requests) == 2
                assert all(
                    r.get("agui_provider_probe") == "profile-loaded"
                    for r in peer.requests
                )
                assert all(
                    h.get("Authorization") == "Bearer local-profile-secret-only"
                    for h in peer.request_headers
                )
                assert all(
                    any(t["function"]["name"] == peer.tool_name for t in r["tools"])
                    for r in peer.requests
                )
        finally:
            failure = sys.exc_info()[1]
            process.terminate()
            try:
                _, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate(timeout=5)
            if failure is not None:
                failure.add_note(stderr[-7000:])
        assert process.returncode == -signal.SIGTERM, stderr
        assert "Traceback" not in stderr
