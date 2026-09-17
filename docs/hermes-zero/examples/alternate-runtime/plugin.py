from hermes_agent_sdk.messages import Message
from hermes_agent_sdk.runtime import TurnRequest, TurnResult


class EchoRuntime:
    def run(self, request: TurnRequest) -> TurnResult:
        text = f"alternate:{request.text}"
        messages = list(request.messages) + [
            Message(role="user", content=request.text),
            Message(role="assistant", content=text),
        ]
        return TurnResult(text=text, messages=messages)

    def cancel(self) -> None:
        return None


def register(ctx) -> None:
    ctx.register_service("agent.runtime", EchoRuntime())
