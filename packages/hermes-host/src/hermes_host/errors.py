"""Host errors. Application plugins must not catch these to invent fallbacks."""


class HostError(Exception):
    """Base error for the plugin host."""


class CapabilityError(HostError):
    """A requested application capability is not part of this composition."""


class PluginError(HostError):
    """A plugin failed validation, import, registration, or lifecycle."""


class CompositionError(HostError):
    """The enabled set cannot be resolved into a runnable composition."""


class AuthorizationError(HostError):
    """A host-mediated privileged operation was denied (fail closed)."""
