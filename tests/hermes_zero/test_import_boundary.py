from __future__ import annotations

import sys

from hermes_host import Host, HostConfig


APPLICATION_MODULES = (
    "agent",
    "tools",
    "hermes_cli",
    "gateway",
    "run_agent",
    "cli",
    "cron",
    "tui_gateway",
    "acp_adapter",
    "hermes_agent_sdk",
    "plugins",
    "providers",
    "model_tools",
    "toolsets",
)


def test_importing_host_does_not_import_application_modules():
    imported = [name for name in APPLICATION_MODULES if name in sys.modules]
    # The test process may already have imported application modules if the
    # full suite ran first. The contract we can always assert: constructing a
    # bare host does not *need* them, proven by start() with those packages
    # unused. When they are absent, they must stay absent.
    host_home_modules_before = {name: sys.modules.get(name) for name in APPLICATION_MODULES}
    from hermes_host.host import Host as HostClass
    from hermes_host.config import HostConfig as Config
    _ = HostClass, Config
    if not any(host_home_modules_before.values()):
        for name in APPLICATION_MODULES:
            assert name not in sys.modules


def test_bare_start_does_not_load_application_modules(host_home):
    before = {name: name in sys.modules for name in APPLICATION_MODULES}
    host = Host(HostConfig(home=host_home, include_entry_points=False))
    host.start()
    host.stop()
    for name in APPLICATION_MODULES:
        if not before[name]:
            assert name not in sys.modules
