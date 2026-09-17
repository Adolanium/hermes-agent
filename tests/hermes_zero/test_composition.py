from __future__ import annotations

from hermes_host import CompositionError, Host, HostConfig

from ._factory import write_plugin

COUNTER = """
def register(ctx):
    box = {"n": 0}

    class Counter:
        def inc(self):
            box["n"] += 1
            return box["n"]

        def value(self):
            return box["n"]

    ctx.register_service("test.counter", Counter())
"""

PROVIDER_A = """
def register(ctx):
    ctx.register_service("model.provider", type("A", (), {"id": "a"})())
"""

PROVIDER_B = """
def register(ctx):
    ctx.register_service("model.provider", type("B", (), {"id": "b"})())
"""


def test_dependency_cycle_is_rejected(host_home):
    plugins = host_home / "plugins"
    write_plugin(plugins, "cycle.a", "def register(ctx):\n    pass\n", depends=[{"plugin": "cycle.b"}])
    write_plugin(plugins, "cycle.b", "def register(ctx):\n    pass\n", depends=[{"plugin": "cycle.a"}])
    host = Host(HostConfig(home=host_home, enabled=("cycle.a", "cycle.b"), include_entry_points=False))
    try:
        host.start()
        raise AssertionError("cycle must fail")
    except CompositionError as exc:
        assert "cycle" in str(exc).lower()


def test_ambiguous_unique_service_requires_explicit_selection(host_home):
    plugins = host_home / "plugins"
    write_plugin(plugins, "prov.a", PROVIDER_A, provides=[{"service": "model.provider", "unique": True}])
    write_plugin(plugins, "prov.b", PROVIDER_B, provides=[{"service": "model.provider", "unique": True}])
    host = Host(HostConfig(home=host_home, enabled=("prov.a", "prov.b"), include_entry_points=False))
    try:
        host.start()
        raise AssertionError("ambiguous unique service must fail")
    except CompositionError as exc:
        assert "model.provider" in str(exc)


def test_service_selection_picks_one_unique_provider(host_home):
    plugins = host_home / "plugins"
    write_plugin(plugins, "prov.a", PROVIDER_A, provides=[{"service": "model.provider", "unique": True}])
    write_plugin(plugins, "prov.b", PROVIDER_B, provides=[{"service": "model.provider", "unique": True}])
    host = Host(
        HostConfig(
            home=host_home,
            enabled=("prov.a", "prov.b"),
            service_selection={"model.provider": "prov.b"},
            include_entry_points=False,
        )
    )
    host.start()
    try:
        assert host.get_service("model.provider").id == "b"
    finally:
        host.stop()


def test_missing_required_service_does_not_silently_fallback(host_home):
    plugins = host_home / "plugins"
    write_plugin(
        plugins,
        "needs.runtime",
        "def register(ctx):\n    pass\n",
        requires=[{"service": "agent.runtime"}],
    )
    host = Host(HostConfig(home=host_home, enabled=("needs.runtime",), include_entry_points=False))
    try:
        host.start()
        raise AssertionError("missing required service must fail")
    except CompositionError as exc:
        assert "agent.runtime" in str(exc)
