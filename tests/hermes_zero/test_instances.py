from __future__ import annotations

from hermes_host import Host, HostConfig

from ._factory import write_plugin

COUNTER = """
def register(ctx):
    box = {"n": 0}
    class Counter:
        def inc(self):
            box["n"] += 1
            return box["n"]
    ctx.register_service("test.counter", Counter())
"""


def test_two_hosts_do_not_share_service_state(host_home, tmp_path):
    plugins = tmp_path / "shared-plugins"
    write_plugin(plugins, "iso.counter", COUNTER, provides=[{"service": "test.counter"}])
    home_a = host_home / "a"
    home_b = host_home / "b"
    home_a.mkdir()
    home_b.mkdir()
    host_a = Host(HostConfig(home=home_a, enabled=("iso.counter",), search_paths=(plugins,), include_entry_points=False))
    host_b = Host(HostConfig(home=home_b, enabled=("iso.counter",), search_paths=(plugins,), include_entry_points=False))
    host_a.start()
    host_b.start()
    try:
        assert host_a.get_service("test.counter").inc() == 1
        assert host_b.get_service("test.counter").inc() == 1
        assert host_a.get_service("test.counter").inc() == 2
        assert host_b.get_service("test.counter").inc() == 2
    finally:
        host_a.stop()
        host_b.stop()
