from hermes_agent_sdk.messages import ToolCall, ToolResult


class ShoutTool:
    name = "shout"
    description = "Uppercase the provided text."
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def invoke(self, call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call_id=call.id,
            name=self.name,
            content=str(call.arguments.get("text", "")).upper(),
        )


def register(ctx) -> None:
    registry = ctx.get_service("tool.registry")
    tool = ShoutTool()
    registry.register(tool)
    ctx.register_service("tool.shout", tool, unique=False)
