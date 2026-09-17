# hermes-host

The Hermes Zero kernel. This package starts, composes, and stops plugins. It does not
run conversations, talk to model providers, register tools, or open a TUI.

```bash
python -m venv .venv
.venv/bin/pip install hermes-host   # or: pip install ./packages/hermes-host
hermes-host --home /tmp/hz status
```

With zero plugins enabled the process:

- reads host configuration
- discovers plugin *metadata* without importing plugin code
- reports the empty composition
- exits without network access or background application services

Application behavior arrives only when plugins are installed **and** explicitly enabled.
