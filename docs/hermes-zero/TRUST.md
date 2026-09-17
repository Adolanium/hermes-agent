# Trust model

In-process Python plugins run with the host process privileges. Manifests and
`HostContext.authorize` govern **cooperative** use of host-mediated services.
They do not sandbox arbitrary code, contain native crashes, or stop a
blocking `while True`.

Rules the kernel actually enforces:

- Disabled plugins are not imported.
- Missing `policy.privilege` denies privileged operations (fail closed).
- Plugin data lives under `<home>/plugin-data/<plugin-id>/`, not in the install tree.
- Unique services cannot be claimed by an unselected plugin.
- First-party plugins use the same `register(ctx)` entry as third-party plugins.

Filesystem reads/writes go through `hermes.tools.fs`, which calls
`ctx.authorize("fs.read"|"fs.write", path=...)`. `hermes.policy.workspace`
allows only paths under its configured workspace root.
