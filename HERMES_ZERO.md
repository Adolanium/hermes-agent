# Hermes Zero

CLI-only Hermes Agent. The TUI, desktop app, dashboard, and messaging
gateways are not part of this build. Optional surfaces are plugins and
are not installed by default.

```bash
hermes query "what files are in this directory?"
hermes tools
hermes read README.md
```

Bare `hermes` prints help and exits. It does not open a TUI or sit on a
prompt.

Data for the plugin host lives in `./.hermes-zero`, not `~/.hermes`.
`hermes query` uses the real agent loop (`hermes_cli.oneshot`) when the
source tree is present; otherwise it uses the small plugin runtime.

See `docs/hermes-zero/ARCHITECTURE.md`.
