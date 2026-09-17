from __future__ import annotations

from typing import Any

from hermes_agent_sdk.messages import ToolCall, ToolResult


class EchoTool:
    name = "echo"
    description = "Return the provided text unchanged."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def invoke(self, call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call_id=call.id,
            name=self.name,
            content=str(call.arguments.get("text", "")),
        )


class InProcessToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def register(self, tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def invoke(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=f"unknown tool: {call.name}",
                is_error=True,
            )
        return tool.invoke(call)


def register(ctx) -> None:
    registry = InProcessToolRegistry()
    echo = EchoTool()
    registry.register(echo)
    ctx.register_service("tool.registry", registry)
    ctx.register_service("tool.echo", echo, unique=False)

    def tools_cmd(_argv: list[str]) -> int:
        for schema in registry.schemas():
            function = schema.get("function") or {}
            print(f"{function.get('name', ''):16} {function.get('description', '')}")
        return 0

    ctx.register_command("tools", tools_cmd, help="List programming tools and exit")
