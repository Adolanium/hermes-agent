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

    def terminal_cmd(argv: list[str]) -> int:
        cwd = str(Path.cwd())
        command_parts: list[str] = []
        i = 0
        while i < len(argv):
            token = argv[i]
            if token == "--cwd" and i + 1 < len(argv):
                cwd = argv[i + 1]
                i += 2
                continue
            if token.startswith("--cwd="):
                cwd = token.split("=", 1)[1]
                i += 1
                continue
            command_parts = argv[i:]
            break
        if not command_parts:
            print("usage: hermes terminal --cwd <dir> <command...>")
            return 2
        result = tool.invoke(
            ToolCall(
                id="cli",
                name="terminal",
                arguments={"command": " ".join(command_parts), "cwd": str(Path(cwd).expanduser().resolve())},
            )
        )
        print(result.content, end="" if result.content.endswith("\n") else "\n")
        return 1 if result.is_error else 0

    ctx.register_command("terminal", terminal_cmd, help="Run a workspace command and exit")
