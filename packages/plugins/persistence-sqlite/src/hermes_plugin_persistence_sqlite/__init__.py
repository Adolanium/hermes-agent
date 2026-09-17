from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from hermes_agent_sdk.messages import Message


class SqliteSessionStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, messages TEXT NOT NULL)"
        )
        self._conn.commit()

    def load(self, session_id: str) -> list[Message]:
        row = self._conn.execute("SELECT messages FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return []
        raw = json.loads(row[0])
        return [Message(**item) for item in raw]

    def save(self, session_id: str, messages: list[Message]) -> None:
        payload = json.dumps(
            [
                {
                    "role": message.role,
                    "content": message.content,
                    "name": message.name,
                    "tool_call_id": message.tool_call_id,
                    "extra": message.extra,
                }
                for message in messages
            ]
        )
        self._conn.execute(
            "INSERT INTO sessions(id, messages) VALUES(?, ?) ON CONFLICT(id) DO UPDATE SET messages=excluded.messages",
            (session_id, payload),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def register(ctx) -> None:
    store = SqliteSessionStore(ctx.data_dir() / "sessions.sqlite")
    ctx.register_service("persistence.sessions", store)
    ctx.on_stop(store.close)
