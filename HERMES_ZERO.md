# Hermes Zero

Architectural fork: the mandatory install is a plugin host. Application
behavior is optional.

Start here: `docs/hermes-zero/ARCHITECTURE.md`

```bash
# Bare host (no application plugins)
uv build --wheel packages/hermes-host
uv venv .hz && uv pip install --python .hz dist/hermes_host-*.whl
hermes-host --home /tmp/hz-home init
hermes-host --home /tmp/hz-home status
```

This branch does **not** migrate `~/.hermes`. Always pass `--home`.
