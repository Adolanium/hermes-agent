"""Fail-closed privilege gate. Missing policy is deny, never allow."""

from __future__ import annotations

from typing import Any, Protocol

from hermes_host.errors import AuthorizationError


class PrivilegePolicy(Protocol):
    def authorize(self, plugin_id: str, operation: str, details: dict[str, Any]) -> None:
        """Raise AuthorizationError when the operation is not allowed."""


class FailClosedPolicy:
    """Default host policy: deny every privileged operation until a plugin replaces it."""

    def authorize(self, plugin_id: str, operation: str, details: dict[str, Any]) -> None:
        raise AuthorizationError(
            f"no privilege policy is registered; denied {operation!r} for plugin {plugin_id!r}"
        )


def resolve_policy(service: PrivilegePolicy | None) -> PrivilegePolicy:
    return service if service is not None else FailClosedPolicy()
