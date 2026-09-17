from __future__ import annotations

from typing import Any, Protocol

from hermes_agent_sdk.messages import ToolCall, ToolResult


class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]

    def invoke(self, call: ToolCall) -> ToolResult:
        ...


class ToolRegistry(Protocol):
    def register(self, tool: Tool) -> None:
        ...

    def schemas(self) -> list[dict[str, Any]]:
        ...

    def invoke(self, call: ToolCall) -> ToolResult:
        ...
