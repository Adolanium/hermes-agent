from __future__ import annotations

from hermes_host import Host, HostConfig, PluginError

from ._factory import write_plugin

GOOD = """
def register(ctx):
    marker = ctx.data_dir() / "started"
    marker.write_text("1", encoding="utf-8")
    ctx.register_service("test.good", object())
    def stop():
        marker.write_text("stopped", encoding="utf-8")
    ctx.on_stop(stop)
"""

BAD = """
def register(ctx):
    raise RuntimeError("activation failed")
"""


def test_failed_activation_rolls_back_started_plugin(host_home):
    plugins = host_home / "plugins"
    write_plugin(plugins, "life.good", GOOD, provides=[{"service": "test.good"}])
    write_plugin(plugins, "life.bad", BAD, depends=[{"plugin": "life.good"}])
    host = Host(HostConfig(home=host_home, enabled=("life.good", "life.bad"), include_entry_points=False))
    try:
        host.start()
        raise AssertionError("activation failure must fail the host")
    except PluginError:
        pass
    marker = host.config.plugins_data_dir / "life.good" / "started"
    assert marker.read_text(encoding="utf-8") == "stopped"
    assert host.find_service("test.good") is None
    assert not host.running


def test_shutdown_clears_services_and_second_start_does_not_duplicate(host_home):
    plugins = host_home / "plugins"
    write_plugin(
        plugins,
        "life.once",
        """
def register(ctx):
    ctx.register_service("test.once", object())
""",
        provides=[{"service": "test.once"}],
    )
    host = Host(HostConfig(home=host_home, enabled=("life.once",), include_entry_points=False))
    host.start()
    first = host.get_service("test.once")
    host.stop()
    host.start()
    try:
        second = host.get_service("test.once")
        assert second is not first
        assert host._registry.all("test.once") == (second,)
    finally:
        host.stop()


def test_cancel_is_visible_to_plugins(host_home):
    plugins = host_home / "plugins"
    write_plugin(
        plugins,
        "life.cancel",
        """
def register(ctx):
    class Gate:
        def __init__(self, ctx):
            self.ctx = ctx
        def cancelled(self):
            return self.ctx.cancelled
    ctx.register_service("test.gate", Gate(ctx))
""",
        provides=[{"service": "test.gate"}],
    )
    host = Host(HostConfig(home=host_home, enabled=("life.cancel",), include_entry_points=False))
    host.start()
    try:
        gate = host.get_service("test.gate")
        assert gate.cancelled() is False
        host.cancel()
        assert gate.cancelled() is True
    finally:
        host.stop()


def test_privileged_operation_fails_closed_without_policy(host_home):
    plugins = host_home / "plugins"
    write_plugin(
        plugins,
        "life.priv",
        """
from hermes_host.errors import AuthorizationError

def register(ctx):
    class Probe:
        def __init__(self, ctx):
            self.ctx = ctx
        def poke(self):
            self.ctx.authorize("fs.write", path="/tmp/x")
    ctx.register_service("test.probe", Probe(ctx))
""",
        provides=[{"service": "test.probe"}],
    )
    host = Host(HostConfig(home=host_home, enabled=("life.priv",), include_entry_points=False))
    host.start()
    try:
        from hermes_host.errors import AuthorizationError
        try:
            host.get_service("test.probe").poke()
            raise AssertionError("missing policy must deny")
        except AuthorizationError:
            pass
    finally:
        host.stop()
