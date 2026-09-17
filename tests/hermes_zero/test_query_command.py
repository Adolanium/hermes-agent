from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hermes_host.cli import main as host_main
from hermes_host.config import HostConfig, write_host_config

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SRC_DIRS = [
    ROOT / "packages" / "plugins" / "persistence" / "src",
    ROOT / "packages" / "plugins" / "tools-core" / "src",
    ROOT / "packages" / "plugins" / "openai-compat" / "src",
    ROOT / "packages" / "plugins" / "agent-runtime" / "src",
    ROOT / "packages" / "plugins" / "cli-stdio" / "src",
]


def test_query_command_runs_one_turn(host_home, capsys):
    for path in PLUGIN_SRC_DIRS:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
            blob = json.dumps({"choices": [{"message": {"role": "assistant", "content": "pong"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def log_message(self, format, *args):  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        write_host_config(
            HostConfig(
                home=host_home,
                enabled=(
                    "hermes.persistence",
                    "hermes.tools.core",
                    "hermes.provider.openai-compat",
                    "hermes.agent.runtime",
                    "hermes.interface.stdio",
                ),
                search_paths=tuple(PLUGIN_SRC_DIRS),
                include_entry_points=False,
                plugin_settings={
                    "hermes.provider.openai-compat": {
                        "base_url": f"http://127.0.0.1:{server.server_address[1]}/v1",
                        "api_key": "test",
                        "model": "fixture",
                    }
                },
            )
        )
        rc = host_main(["--home", str(host_home), "query", "ping"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "pong" in captured.out
    finally:
        server.shutdown()
