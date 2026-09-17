from __future__ import annotations

import json
from pathlib import Path

from hermes_agent_sdk.messages import Message


class JsonSessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in session_id)
        return self.root / f"{safe}.json"

    def load(self, session_id: str) -> list[Message]:
        path = self._path(session_id)
        if not path.is_file():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Message(**item) for item in raw]

    def save(self, session_id: str, messages: list[Message]) -> None:
        payload = [
            {
                "role": message.role,
                "content": message.content,
                "name": message.name,
                "tool_call_id": message.tool_call_id,
                "extra": message.extra,
            }
            for message in messages
        ]
        path = self._path(session_id)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def register(ctx) -> None:
    ctx.register_service("persistence.sessions", JsonSessionStore(ctx.data_dir() / "sessions"))
