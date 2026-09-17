# Measurements

Recorded against starting commit `5cc81773b2` in worktree `E:\Dev\Hermes\hermes-zero`.

## Before (mandatory hermes-agent install)

- Production Python in core-ish trees: **1693 files / ~608116 lines**
- Test Python: **4516 files**
- Direct mandatory deps: openai, certifi, python-dotenv, fire, httpx, rich, tenacity, pyyaml, ruamel.yaml, requests, jinja2, firecrawl-anydoc, pydantic, prompt_toolkit, croniter, snowballstemmer, packaging, Markdown, PyJWT, urllib3, cryptography, psutil, websockets, pathspec, fastapi, uvicorn, python-multipart, ptyprocess/pywinpty, Pillow, pillow-heif, plus Windows/native extras
- Entry points: `hermes`, `hermes-agent`, `hermes-acp` all enter the application

Commands:

```text
# file counts
python -c "..."  # see implementation notes in the refactor session
```

## After (mandatory hermes-host install)

- Kernel package: `packages/hermes-host` — PyYAML + packaging only
- Domain SDK (`hermes-agent-sdk`) is **not** a kernel dependency
- Application plugins are separate distributions
- Bare host startup imports neither `agent` nor `tools`

Repeatable commands:

```bash
pip wheel packages/hermes-host -w dist --no-deps
python -m venv /tmp/hz
/tmp/hz/bin/pip install dist/hermes_host-*.whl
/tmp/hz/bin/hermes-host --home /tmp/hz-home status
```

Idle memory and cold-start timings are recorded when the packaging test runs in CI; they are environment-specific and must not be compared as a fake “deleted 600k lines” story. Code moved into plugins is **moved**, not deleted.
