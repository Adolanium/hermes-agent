# Hermes Zero examples

These plugins live **outside** `packages/` and use only public contracts.

## Alternate runtime

Proves the kernel is not coupled to `hermes.agent.runtime`.

```bash
hermes-host --home /tmp/hz plugins enable example.alternate-runtime
# point plugins.search_paths at docs/hermes-zero/examples/
```

Select it with:

```toml
[services]
"agent.runtime" = "example.alternate-runtime"
```

## External shout tool

Adds a `shout` tool through `tool.registry`. Removing it leaves `echo` working.
