from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from hermes_agent_sdk.messages import Message, ToolCall
from hermes_agent_sdk.provider import CompletionRequest, CompletionResult


class OpenAICompatProvider:
    id = "openai-compat"

    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def complete(self, request: CompletionRequest) -> CompletionResult:
        if not self.base_url or self.base_url.rstrip("/").endswith("://127.0.0.1:0") or self.base_url.endswith("127.0.0.1:0/v1"):
            raise RuntimeError(
                "model provider is not configured. Set plugins.settings.\"hermes.provider.openai-compat\" "
                "base_url (and api_key if required) in host.toml, then re-run. "
                "This CLI does not wait for interactive input."
            )
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": request.model or self.model,
            "messages": [_message_payload(message) for message in request.messages],
        }
        if request.tools:
            payload["tools"] = request.tools
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"openai-compat request failed: {exc}") from exc
        choice = ((raw.get("choices") or [{}])[0]).get("message") or {}
        tool_calls = []
        for item in choice.get("tool_calls") or []:
            function = item.get("function") or {}
            arguments = function.get("arguments") or "{}"
            if isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    parsed = {"_raw": arguments}
            else:
                parsed = dict(arguments)
            tool_calls.append(
                ToolCall(id=str(item.get("id") or "call"), name=str(function.get("name") or ""), arguments=parsed)
            )
        return CompletionResult(text=str(choice.get("content") or ""), tool_calls=tool_calls, raw=raw)


def _message_payload(message: Message) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.name:
        payload["name"] = message.name
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if message.extra.get("tool_calls"):
        payload["tool_calls"] = message.extra["tool_calls"]
    return payload


def register(ctx) -> None:
    settings = ctx.settings()
    provider = OpenAICompatProvider(
        base_url=str(settings.get("base_url") or ""),
        api_key=str(settings.get("api_key") or ""),
        model=str(settings.get("model") or "gpt-4o-mini"),
    )
    ctx.register_service("model.provider", provider)
