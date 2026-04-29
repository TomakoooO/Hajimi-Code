from dataclasses import dataclass, field
from time import time
from uuid import uuid4


@dataclass
class Message:
    role: str
    content: str
    ts: int = field(default_factory=lambda: int(time() * 1000))


@dataclass
class SessionData:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    updated_at: int = field(default_factory=lambda: int(time() * 1000))


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}

    def ensure_session(self, session_id: str | None = None) -> SessionData:
        sid = session_id or f"s-{uuid4().hex[:10]}"
        if sid not in self._sessions:
            self._sessions[sid] = SessionData(session_id=sid)
        return self._sessions[sid]

    def append_message(self, session_id: str, role: str, content: str) -> None:
        session = self.ensure_session(session_id)
        session.messages.append(Message(role=role, content=content))
        session.updated_at = int(time() * 1000)

    def get_session(self, session_id: str) -> SessionData | None:
        return self._sessions.get(session_id)


session_store = InMemorySessionStore()
