import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.response import ok
from app.services.timeline_store import TimelineEvent, timeline_store
from app.core.logging_config import subscribe_logs

router = APIRouter()

@router.websocket("/ws/logs")
async def logs_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue()

    def _on_log(msg: str) -> None:
        queue.put_nowait(msg)

    unsub = subscribe_logs(_on_log)
    try:
        while True:
            msg_task = asyncio.create_task(queue.get())
            recv_task = asyncio.create_task(websocket.receive())
            done, pending = await asyncio.wait(
                [msg_task, recv_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if recv_task in done:
                break
            msg = msg_task.result()
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass
    finally:
        unsub()

@router.get("/timeline/replay/{request_id}")
def replay_timeline(request_id: str) -> dict:
    return ok({"request_id": request_id, "events": timeline_store.replay(request_id)})


@router.websocket("/ws/timeline")
async def timeline_ws(websocket: WebSocket, request_id: str | None = Query(default=None)) -> None:
    await websocket.accept()
    queue: asyncio.Queue[TimelineEvent] = asyncio.Queue()

    def _on_event(event: TimelineEvent) -> None:
        if request_id and event.request_id != request_id:
            return
        queue.put_nowait(event)

    unsub = timeline_store.subscribe(_on_event)
    try:
        await websocket.send_json({"type": "status", "connected": True, "request_id": request_id})
        while True:
            msg_task = asyncio.create_task(queue.get())
            recv_task = asyncio.create_task(websocket.receive())
            done, pending = await asyncio.wait(
                [msg_task, recv_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if recv_task in done:
                break
            event = msg_task.result()
            await websocket.send_json(
                {
                    "type": "timeline",
                    "event": event.__dict__,
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        unsub()


async def _iter_queue(queue: asyncio.Queue[TimelineEvent]) -> AsyncGenerator[TimelineEvent, None]:
    while True:
        event = await queue.get()
        yield event
