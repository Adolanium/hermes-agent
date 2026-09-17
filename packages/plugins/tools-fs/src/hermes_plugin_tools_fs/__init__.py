from __future__ import annotations

from pathlib import Path

from hermes_agent_sdk.messages import ToolCall, ToolResult


class _FsTool:
    def __init__(self, ctx) -> None:
        self._ctx = ctx

    def _invoke(self, operation: str, call: ToolCall, *, write: bool = False) -> ToolResult:
        path = str(call.arguments.get("path") or "")
        try:
            self._ctx.authorize(operation, path=path)
        except Exception as exc:
            return ToolResult(tool_call_id=call.id, name=self.name, content=str(exc), is_error=True)
        target = Path(path)
        try:
            if write:
                target.write_text(str(call.arguments.get("content") or ""), encoding="utf-8")
                return ToolResult(tool_call_id=call.id, name=self.name, content=f"wrote {target}")
            if not target.is_file():
                return ToolResult(tool_call_id=call.id, name=self.name, content="file not found", is_error=True)
            return ToolResult(tool_call_id=call.id, name=self.name, content=target.read_text(encoding="utf-8"))
        except OSError as exc:
            return ToolResult(tool_call_id=call.id, name=self.name, content=str(exc), is_error=True)


class ReadFileTool(_FsTool):
    name = "read_file"
    description = "Read a UTF-8 text file inside the authorized workspace."
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def invoke(self, call: ToolCall) -> ToolResult:
        return self._invoke("fs.read", call)


class WriteFileTool(_FsTool):
    name = "write_file"
    description = "Write a UTF-8 text file inside the authorized workspace."
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    def invoke(self, call: ToolCall) -> ToolResult:
        return self._invoke("fs.write", call, write=True)


def register(ctx) -> None:
    registry = ctx.get_service("tool.registry")
    for tool in (ReadFileTool(ctx), WriteFileTool(ctx)):
        registry.register(tool)
    ctx.register_service("tool.fs", True, unique=False)
