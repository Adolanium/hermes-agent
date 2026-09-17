from __future__ import annotations

from hermes_agent_sdk.runtime import TurnRequest, TurnResult


class StdioInterface:
    def __init__(self, ctx) -> None:
        self._ctx = ctx

    def run_text(self, text: str, session_id: str = "default") -> TurnResult:
        runtime = self._ctx.get_service("agent.runtime")
        return runtime.run(TurnRequest(text=text, session_id=session_id))


def register(ctx) -> None:
    interface = StdioInterface(ctx)
    ctx.register_service("interface.stdio", interface)

    def query(argv: list[str]) -> int:
        text = " ".join(argv).strip()
        if not text:
            print("usage: hermes-host --home <dir> query <text>")
            return 2
        result = interface.run_text(text)
        print(result.text)
        return 1 if result.error else 0

    ctx.register_command("query", query, help="Run one agent turn on stdout")
