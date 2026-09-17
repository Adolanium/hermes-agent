from __future__ import annotations

from typing import Protocol

from hermes_agent_sdk.messages import Message


class SessionStore(Protocol):
    def load(self, session_id: str) -> list[Message]:
        ...

    def save(self, session_id: str, messages: list[Message]) -> None:
        ...
