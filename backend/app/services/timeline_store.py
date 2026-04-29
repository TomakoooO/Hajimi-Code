from collections import defaultdict
from dataclasses import dataclass
from time import time
from typing import Callable
from uuid import uuid4


@dataclass
class TimelineEvent:
    id: str
    request_id: str
    actor: str
    event: str
    payload: dict
    ts: int


class TimelineStore:
    def __init__(self) -> None:
        self._events: dict[str, list[TimelineEvent]] = defaultdict(list)
        self._subs: list[Callable[[TimelineEvent], None]] = []

    def publish(self, request_id: str, actor: str, event: str, payload: dict | None = None) -> TimelineEvent:
        item = TimelineEvent(
            id=f"ev-{uuid4().hex[:12]}",
            request_id=request_id,
            actor=actor,
            event=event,
            payload=payload or {},
            ts=int(time() * 1000),
        )
        self._events[request_id].append(item)
        for callback in list(self._subs):
            callback(item)
        return item

    def replay(self, request_id: str) -> list[dict]:
        return [event.__dict__ for event in self._events.get(request_id, [])]

    def subscribe(self, callback: Callable[[TimelineEvent], None]) -> Callable[[], None]:
        self._subs.append(callback)

        def _unsub() -> None:
            if callback in self._subs:
                self._subs.remove(callback)

        return _unsub


timeline_store = TimelineStore()
