"""Hermes Zero kernel: compose plugins, implement none of them."""

from hermes_host.api import ENTRY_POINTS_GROUP, HOST_API_VERSION
from hermes_host.config import HostConfig
from hermes_host.errors import (
    AuthorizationError,
    CapabilityError,
    CompositionError,
    HostError,
    PluginError,
)
from hermes_host.host import Host
from hermes_host.metadata import PluginMetadata

__all__ = [
    "ENTRY_POINTS_GROUP",
    "HOST_API_VERSION",
    "AuthorizationError",
    "CapabilityError",
    "CompositionError",
    "Host",
    "HostConfig",
    "HostError",
    "PluginError",
    "PluginMetadata",
]
