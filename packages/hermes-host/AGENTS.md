# packages/hermes-host — Hermes Zero kernel

This package is the **only** mandatory Python distribution. If a module here
knows about conversations, providers, tools, gateways, or UIs, it is in the
wrong package.

## Allowed

- Bootstrap / CLI for host status, plugin metadata listing, enablement, start/stop
- Reading host configuration and plugin metadata files (no plugin imports)
- Dependency resolution, service registry, lifecycle, fail-closed privilege gate
- Generic cancellation and diagnostics

## Forbidden

- Importing `agent`, `tools`, `hermes_cli`, `gateway`, `run_agent`, `cli`,
  `plugins`, `providers`, `cron`, `tui_gateway`, `acp_adapter`
- Importing `hermes_agent_sdk` (domain contracts are optional)
- Default-enabling any application plugin
- Feature-specific settings keys for individual plugins
- Global mutable registries that leak across `Host` instances

Every new module must answer: *why is this needed when zero plugins are installed?*
