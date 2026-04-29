import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.response import err, ok
from app.services.review_store import review_store
from app.services.timeline_store import timeline_store

router = APIRouter()


class SnapshotCreateRequest(BaseModel):
    files: list[str] = Field(default_factory=list)


class SnapshotCommitRequest(BaseModel):
    snapshot_id: str


class ReviewDecisionRequest(BaseModel):
    review_ids: list[str]
    action: str = Field(..., pattern="^(confirm|rollback)$")


@router.post("/review/snapshot")
def create_snapshot(req: SnapshotCreateRequest) -> dict:
    try:
        snap = review_store.create_snapshot(req.files or None)
        return ok(
            {
                "snapshot_id": snap.snapshot_id,
                "workspace_root": snap.workspace_root,
                "file_count": len(snap.files),
                "ts": snap.ts,
            }
        )
    except ValueError as exc:
        return err(code=40001, message=str(exc), status=400)


@router.post("/review/commit")
def commit_snapshot(req: SnapshotCommitRequest) -> dict:
    try:
        review = review_store.commit_snapshot(req.snapshot_id)
        timeline_store.publish(
            request_id=req.snapshot_id,
            actor="review",
            event="commit",
            payload={"review_id": review.review_id, "files": len(review.files)},
        )
        return ok(review_store.serialize_review(review))
    except ValueError as exc:
        return err(code=40002, message=str(exc), status=400)


@router.post("/review/decision")
def decide_review(req: ReviewDecisionRequest) -> dict:
    try:
        data = review_store.decide(req.review_ids, req.action)
        timeline_store.publish(
            request_id=f"review-{req.action}",
            actor="review",
            event=f"decision.{req.action}",
            payload=data,
        )
        return ok(data)
    except ValueError as exc:
        return err(code=40003, message=str(exc), status=400)


@router.get("/review/pending")
def pending_reviews() -> dict:
    return ok({"reviews": review_store.list_pending()})


@router.websocket("/ws/review")
async def review_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    def _on_event(event: dict) -> None:
        queue.put_nowait(event)

    unsub = review_store.subscribe(_on_event)
    try:
        await websocket.send_json({"type": "status", "connected": True})
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
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        unsub()


async def _iter_queue(queue: asyncio.Queue[dict]) -> AsyncGenerator[dict, None]:
    while True:
        event = await queue.get()
        yield event
