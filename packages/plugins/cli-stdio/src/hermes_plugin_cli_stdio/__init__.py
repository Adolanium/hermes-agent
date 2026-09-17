from __future__ import annotations

from hermes_agent_sdk.runtime import TurnRequest, TurnResult


class StdioInterface:
    def __init__(self, ctx) -> None:
        self._ctx = ctx

    def run_text(self, text: str, session_id: str = "default") -> TurnResult:
        runtime = self._ctx.get_service("agent.runtime")
        return runtime.run(TurnRequest(text=text, session_id=session_id))


def register(ctx) -> None:
    ctx.register_service("interface.stdio", StdioInterface(ctx))
