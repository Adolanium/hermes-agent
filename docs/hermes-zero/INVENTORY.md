# Capability inventory

Baseline (commit `5cc81773b2`): ~1693 production Python files / ~608k lines in agent+tools+cli+gateway+plugins+root modules. ~4516 test files. Mandatory deps currently include openai, fastapi, uvicorn, prompt_toolkit, Pillow, croniter, websockets, pydantic, and more.

| Capability | Original location | Target owner | Status |
|---|---|---|---|
| Plugin host | `hermes_cli/plugins*.py` | `hermes-host` | **migrated** (new host; old manager still in tree) |
| Agent loop | `run_agent.py`, `agent/turn_*.py` | `hermes.agent.runtime` | **slice implemented** (new loop). Old loop still in tree. |
| OpenAI-compat HTTP | `agent` + `openai` core dep | `hermes.provider.openai-compat` | **slice implemented** |
| Tool registry + echo | `tools/registry.py`, `model_tools.py` | `hermes.tools.core` | **slice implemented** (echo only) |
| Session persistence | `hermes_state*.py` | `hermes.persistence` (JSON) / `hermes.persistence.sqlite` | **slice implemented** (not the production SessionDB) |
| Stdio interface | `cli.py` / `hermes_cli` | `hermes.interface.stdio` | **slice implemented** |
| File tools | `tools/file_*.py` | `hermes.tools.fs` | **slice implemented** (UTF-8 read/write + workspace policy; not the full tool surface) |
| Workspace policy | `tools/approval*.py` / path guards | `hermes.policy.workspace` | **slice implemented** (path root only; not session approvals) |
| Terminal tools | `tools/terminal_*.py` | `hermes.tools.terminal` | **slice implemented** (cwd-gated subprocess; not docker/ssh/modal backends) |
| Approvals / interactive policy | `tools/approval*.py` | policy plugin | unfinished (kernel fail-closed; workspace policy covers path/cwd) |
| SQLite state | `hermes_state*.py` | `hermes.persistence.sqlite` | **slice implemented** (sessions table only; not FTS/rewind/profiles) |
| Memory providers | `plugins/memory/` | keep as plugins | unfinished (not on Zero host) |
| Model providers (40+) | `plugins/model-providers/` | provider plugins | unfinished |
| Messaging gateway | `gateway/` | gateway plugin | unfinished |
| Platform adapters | `plugins/platforms/`, `gateway/platforms/` | platform plugins | unfinished |
| Cron | `cron/` | cron plugin | unfinished |
| TUI / desktop / web | `ui-tui/`, `apps/desktop/`, `web/` | interface plugins | unfinished |
| ACP | `acp_adapter/` | acp plugin | unfinished |
| MCP client/server | `tools/mcp_*.py`, `mcp_serve.py` | mcp plugin | unfinished |
| Skills | `skills/`, `optional-skills/` | skills plugin | unfinished |
| Compression / prompt | `agent/context_compressor*`, prompt builder | runtime plugin | unfinished |
| Auth / credentials | `hermes_cli/auth*.py` | auth plugins | unfinished |

"Migrated" means the Zero host owns a working replacement, not that the old tree was deleted.
