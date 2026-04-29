from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.response import ok
from app.models.schemas import ChatAskRequest
from app.services.chat_service import run_chat_stream
from app.services.session_store import session_store, Message
from app.agent.s_full import auto_compact, switch_workspace_root
from app.services.workspace_context import get_workspace_root

router = APIRouter()

class CompactRequest(BaseModel):
    session_id: str

@router.post("/chat/compact")
async def chat_compact(req: CompactRequest):
    session = session_store.get_session(req.session_id)
    if not session:
        return ok({"status": "error", "message": "Session not found"})
        
    history = [{"role": msg.role, "content": msg.content} for msg in session.messages]
    if len(history) <= 1:
        return ok({"status": "ok", "message": "Context already small enough"})
        
    switch_workspace_root(str(get_workspace_root()))
    try:
        compressed_history = auto_compact(history)
        session.messages = [Message(role=m["role"], content=m["content"]) for m in compressed_history]
        return ok({"status": "ok", "message": "Context compressed successfully", "messages": [{"role": m.role, "content": m.content} for m in session.messages]})
    except Exception as e:
        return ok({"status": "error", "message": str(e)})

@router.post("/chat/ask")
async def chat_ask(req: ChatAskRequest):
    return StreamingResponse(
        run_chat_stream(
            message=req.message,
            code_refs=[item.path for item in req.code_refs],
            snippets=[item.model_dump() for item in req.snippets],
            files=[item.model_dump() for item in req.files],
            model=req.model,
            session_id=req.session_id,
        ),
        media_type="text/event-stream"
    )
