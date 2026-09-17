from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from hermes_agent_sdk.messages import Message


@dataclass
class TurnRequest:
    text: str
    session_id: str = "default"
    messages: list[Message] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    text: str
    messages: list[Message] = field(default_factory=list)
    error: str | None = None


class AgentRuntime(Protocol):
    """Replaceable conversation loop. The kernel has no implementation of this."""

    def run(self, request: TurnRequest) -> TurnResult:
        ...

    def cancel(self) -> None:
        ...
