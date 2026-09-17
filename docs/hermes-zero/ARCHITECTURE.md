# Hermes Zero architecture

Starting commit: `5cc81773b2` (`refactor/aux: drop the fallback-only structured-output rung…`)
Branch: `refactor/hermes-zero`
Worktree: `E:\Dev\Hermes\hermes-zero`

This is an architectural fork of Hermes Agent. The mandatory install is a plugin
host. Application behavior is optional plugins. The host does not become Hermes
until those plugins are installed and **explicitly enabled**.

## Kernel responsibilities

Package: `packages/hermes-host` (`hermes-host` on PyPI-style installs)

Allowed:

- Read host configuration from `--home` (never `~/.hermes` by default)
- Discover plugin metadata (JSON/YAML / dist files) **without importing plugin code**
- Resolve enablement, versions, dependency cycles, unique service selection
- Import and start only the enabled set; roll back on failure
- Per-instance service registry, event bus, cancellation, fail-closed privilege gate
- Tiny CLI: `status`, `init`, `plugins list|enable|disable`, `start`, `run`

Forbidden in the kernel:

- Conversation loop, providers, tools, prompts, skills, memory, session DB
- Gateways, cron, TUI, desktop, web, ACP, MCP product behavior
- `PluginContext.llm` / `_cli_ref.agent` and other handles to the old application
- Default-enabling bundled plugins

Every remaining kernel module must answer: *why is this needed with zero plugins?*

## Public contracts

- Kernel contract: `HostContext.register_service` / `get_service` / lifecycle hooks
- Domain contracts (optional package `hermes-agent-sdk`): `AgentRuntime`, `ModelProvider`, `Tool`, `SessionStore`
- The kernel does **not** import `hermes-agent-sdk`

## Compositions (data, not privileged code)

| Preset | File | Meaning |
|---|---|---|
| Bare | `compositions/bare.toml` | No plugins |
| Minimal | `compositions/minimal.toml` | persistence + tools + openai-compat + runtime + stdio |
| Full | `compositions/full.toml` | grows as subsystems are extracted; not a monolith wrapper |

## Why the old PluginManager is not the kernel

`hermes_cli.plugins.PluginContext` is an application façade (tools, platforms, LLM, MCP, CLI, memory). Bundled backends auto-load. Discovery is metadata-first, which we kept; the giant context and auto-load are not.

There is one host: `hermes_host.Host`. Legacy `PluginManager` remains in the tree until its consumers are extracted; it is not used by the Zero kernel.
