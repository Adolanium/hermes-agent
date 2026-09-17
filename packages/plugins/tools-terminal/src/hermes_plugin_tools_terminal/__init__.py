from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from hermes_agent_sdk.messages import ToolCall, ToolResult


class TerminalTool:
    name = "terminal"
    description = "Run a command in an authorized workspace directory."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string"},
        },
        "required": ["command", "cwd"],
    }

    def __init__(self, ctx) -> None:
        self._ctx = ctx

    def invoke(self, call: ToolCall) -> ToolResult:
        command = str(call.arguments.get("command") or "")
        cwd = str(call.arguments.get("cwd") or "")
        try:
            self._ctx.authorize("exec", command=command, cwd=cwd)
        except Exception as exc:
            return ToolResult(tool_call_id=call.id, name=self.name, content=str(exc), is_error=True)
        if not command.strip():
            return ToolResult(tool_call_id=call.id, name=self.name, content="missing command", is_error=True)
        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
            completed = subprocess.run(
                argv,
                cwd=str(Path(cwd).resolve()),
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolResult(tool_call_id=call.id, name=self.name, content=str(exc), is_error=True)
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            output = output or f"exit {completed.returncode}"
            return ToolResult(tool_call_id=call.id, name=self.name, content=output, is_error=True)
        return ToolResult(tool_call_id=call.id, name=self.name, content=output)


def register(ctx) -> None:
    tool = TerminalTool(ctx)
    ctx.get_service("tool.registry").register(tool)
    ctx.register_service("tool.terminal", tool, unique=False)
