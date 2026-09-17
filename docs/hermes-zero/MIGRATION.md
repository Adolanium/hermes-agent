# Migration progress

## Done

- Isolated branch `refactor/hermes-zero` from `5cc81773b2` in worktree `E:\Dev\Hermes\hermes-zero`. Unrelated untracked files in the original checkout were not included.
- Kernel package `hermes-host` with metadata-only discovery, explicit enablement, rollback, multi-instance isolation, fail-closed policy.
- Optional `hermes-agent-sdk` domain contracts.
- First-party plugins: persistence, tools-core, openai-compat, agent-runtime, cli-stdio.
- External example tool and alternate runtime (kernel is not coupled to the first-party loop).
- Architectural tests under `tests/hermes_zero/`.

## Intentionally changed

- Bare host does not read `~/.hermes`. Pass `--home`.
- Plugins are opt-in. Nothing is auto-enabled because it was bundled.
- Unique services require explicit `[services]` selection when multiple providers exist.
- Missing `agent.runtime` is a `CapabilityError`, not a silent built-in loop.

## Unfinished

See `INVENTORY.md`. The old monolith still exists in-tree so existing tests keep a path to the original product. Extraction of file/terminal tools, SQLite state, gateway, CLI, TUI, desktop, cron, MCP, skills, and the 40 model providers onto the Zero host is still required before the old entry points can be removed.

## Data

JSON session files live under `<home>/plugin-data/hermes.persistence/sessions/`. No automatic migration of `~/.hermes/state.db` is performed.
