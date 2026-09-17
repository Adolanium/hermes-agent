from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from hermes_agent_sdk.messages import Message, ToolCall


@dataclass
class CompletionRequest:
    messages: list[Message]
    tools: list[dict[str, Any]] = field(default_factory=list)
    model: str = "default"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    id: str

    def complete(self, request: CompletionRequest) -> CompletionResult:
        ...
