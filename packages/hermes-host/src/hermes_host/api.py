"""Kernel API constants.

Bump ``HOST_API_VERSION`` only when the host/plugin contract is incompatible.
Plugins declare the integer they were built against; the host loads only exact
matches in v1 (no silent forward-compat).
"""

HOST_API_VERSION = 1
ENTRY_POINTS_GROUP = "hermes_host.plugins"
