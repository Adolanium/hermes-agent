from __future__ import annotations

import json
import sys

from hermes_host import HOST_API_VERSION, CapabilityError, Host, HostConfig
from hermes_host.cli import main as host_main
from hermes_host.config import write_host_config


def test_bare_host_starts_without_plugins_or_credentials(host_home, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NOUS_API_KEY", raising=False)
    host = Host(HostConfig(home=host_home, include_entry_points=False))
    before = set(sys.modules)
    composition = host.start()
    try:
        assert composition.selected == ()
        assert host.running
        added_roots = {name.split(".")[0] for name in set(sys.modules) - before}
        forbidden = {"agent", "tools", "hermes_cli", "run_agent", "gateway", "cli", "cron"}
        assert not (added_roots & forbidden)
    finally:
        host.stop()
    assert not host.running


def test_missing_agent_runtime_is_a_capability_error(host_home):
    host = Host(HostConfig(home=host_home, include_entry_points=False))
    host.start()
    try:
        try:
            host.require_capability("agent.runtime", what="agent runtime")
            raise AssertionError("missing runtime must not succeed")
        except CapabilityError as exc:
            assert "agent.runtime" in str(exc)
    finally:
        host.stop()


def test_cli_status_json(host_home):
    write_host_config(HostConfig(home=host_home, include_entry_points=False))
    rc = host_main(["--home", str(host_home), "status"])
    assert rc == 0


def test_cli_refuses_to_run_without_home():
    rc = host_main(["status"])
    assert rc != 0


def test_host_api_version_is_explicit():
    assert HOST_API_VERSION == 1
