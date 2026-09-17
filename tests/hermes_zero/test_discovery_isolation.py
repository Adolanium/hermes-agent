from __future__ import annotations

import sys

from hermes_host import CompositionError, Host, HostConfig, PluginError

from ._factory import write_plugin

BOMB = "raise RuntimeError('disabled plugin executed')\n"


def test_disabled_plugin_with_import_bomb_is_never_imported(host_home):
    plugins = host_home / "plugins"
    write_plugin(plugins, "evil.bomb", BOMB, provides=[{"service": "evil.x"}])
    host = Host(HostConfig(home=host_home, enabled=(), include_entry_points=False))
    host.start()
    try:
        assert not any(name.endswith("evil_bomb") or "evil.bomb" in name for name in sys.modules)
        discovered = [item.id for item in host.discover()]
        assert "evil.bomb" in discovered
    finally:
        host.stop()


def test_unrelated_plugin_with_missing_dependency_does_not_break_bare_host(host_home):
    plugins = host_home / "plugins"
    write_plugin(
        plugins,
        "broken.optional",
        "import totally_missing_hermes_zero_package  # noqa: F401\n\ndef register(ctx):\n    pass\n",
    )
    host = Host(HostConfig(home=host_home, enabled=(), include_entry_points=False))
    host.start()
    host.stop()


def test_enabled_malformed_plugin_fails_with_diagnostics(host_home):
    plugins = host_home / "plugins"
    directory = plugins / "bad_meta"
    directory.mkdir(parents=True)
    (directory / "plugin.json").write_text('{"id": "bad.meta"}\n', encoding="utf-8")
    host = Host(HostConfig(home=host_home, enabled=("bad.meta",), include_entry_points=False))
    try:
        host.start()
        raise AssertionError("malformed enabled plugin must fail")
    except (CompositionError, PluginError) as exc:
        assert "bad.meta" in str(exc)


def test_enabled_plugin_import_failure_is_actionable(host_home):
    plugins = host_home / "plugins"
    write_plugin(plugins, "broken.enabled", BOMB)
    host = Host(HostConfig(home=host_home, enabled=("broken.enabled",), include_entry_points=False))
    try:
        host.start()
        raise AssertionError("enabled bomb must fail")
    except PluginError as exc:
        assert "broken.enabled" in str(exc)
