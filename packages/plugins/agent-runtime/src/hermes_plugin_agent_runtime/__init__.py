from __future__ import annotations

from hermes_agent_sdk.messages import Message
from hermes_agent_sdk.provider import CompletionRequest
from hermes_agent_sdk.runtime import TurnRequest, TurnResult


class LoopRuntime:
    def __init__(self, ctx, *, max_iterations: int = 8) -> None:
        self._ctx = ctx
        self.max_iterations = max_iterations

    def cancel(self) -> None:
        return None

    def run(self, request: TurnRequest) -> TurnResult:
        store = self._ctx.get_service("persistence.sessions")
        provider = self._ctx.get_service("model.provider")
        tools = self._ctx.get_service("tool.registry")
        messages = list(store.load(request.session_id) or [])
        if request.messages:
            messages.extend(request.messages)
        messages.append(Message(role="user", content=request.text))
        last_text = ""
        for _ in range(self.max_iterations):
            if self._ctx.cancelled:
                return TurnResult(text=last_text, messages=messages, error="cancelled")
            completion = provider.complete(
                CompletionRequest(messages=list(messages), tools=tools.schemas())
            )
            last_text = completion.text
            if completion.tool_calls:
                messages.append(
                    Message(
                        role="assistant",
                        content=completion.text,
                        extra={
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {
                                        "name": call.name,
                                        "arguments": _dump_args(call.arguments),
                                    },
                                }
                                for call in completion.tool_calls
                            ]
                        },
                    )
                )
                for call in completion.tool_calls:
                    result = tools.invoke(call)
                    messages.append(
                        Message(
                            role="tool",
                            content=result.content,
                            tool_call_id=result.tool_call_id,
                            name=result.name,
                        )
                    )
                continue
            messages.append(Message(role="assistant", content=completion.text))
            store.save(request.session_id, messages)
            return TurnResult(text=completion.text, messages=messages)
        store.save(request.session_id, messages)
        return TurnResult(text=last_text, messages=messages, error="iteration limit")


def _dump_args(arguments: dict) -> str:
    import json
    return json.dumps(arguments)


def register(ctx) -> None:
    ctx.register_service("agent.runtime", LoopRuntime(ctx))
