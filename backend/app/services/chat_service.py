import json
from typing import AsyncGenerator
from uuid import uuid4

from app.services.file_reader import read_code_by_address
from app.services.review_store import review_store
from app.services.session_store import session_store
from app.services.timeline_store import timeline_store
from app.services.workspace_context import get_workspace_root


async def run_chat_stream(
    message: str,
    code_refs: list[str],
    snippets: list[dict] | None = None,
    files: list[dict] | None = None,
    model: str | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    request_id = f"r-{uuid4().hex[:12]}"
    session = session_store.ensure_session(session_id)
    snippets = snippets or []
    files = files or []
    user_message = message
    attachment_note = []
    if files:
        attachment_note.append(f"文件 {len(files)} 个")
    if snippets:
        attachment_note.append(f"代码片段 {len(snippets)} 个")
    if attachment_note:
        user_message = f"{message}\n\n[附件] " + "，".join(attachment_note)

    session_store.append_message(session.session_id, "user", user_message)
    timeline_store.publish(
        request_id,
        "user",
        "message.sent",
        {"message": message, "snippet_count": len(snippets), "file_count": len(files)},
    )

    ref_summaries: list[dict] = []
    for ref in code_refs:
        try:
            item = read_code_by_address(path=ref, start_line=1, end_line=120)
            ref_summaries.append(
                {
                    "path": item["path"],
                    "language": item["language"],
                    "line_count": item["total_lines"],
                    "preview": item["content"][:400],
                }
            )
            timeline_store.publish(request_id, "tool", "file.read", {"path": item["path"]})
        except Exception as exc:  # noqa: BLE001
            ref_summaries.append({"path": ref, "error": str(exc)})
            timeline_store.publish(request_id, "tool", "file.read.error", {"path": ref, "error": str(exc)})

    timeline_store.publish(request_id, "parent-agent", "planning", {"note": "Invoking full agent loop"})
    
    history = []
    for msg in session.messages:
        history.append({"role": msg.role, "content": msg.content})
    if history and history[-1]["role"] == "user":
        blocks: list[str] = []
        for item in files:
            blocks.append(
                "\n".join(
                    [
                        f"[file] {item.get('path')}",
                        f"```{item.get('language', 'plaintext')}",
                        str(item.get("content", "")),
                        "```",
                    ]
                )
            )
        for item in snippets:
            blocks.append(
                "\n".join(
                    [
                        f"[snippet] {item.get('path')}:{item.get('start_line')}-{item.get('end_line')}",
                        f"```{item.get('language', 'plaintext')}",
                        str(item.get("content", "")),
                        "```",
                    ]
                )
            )
        if blocks:
            history[-1]["content"] = f"{message}\n\n" + "\n\n".join(blocks)

    answer = ""
    llm_info = {"model": "s_full"}
    snapshot = review_store.create_snapshot()
    timeline_store.publish(
        request_id,
        "review",
        "snapshot.created",
        {"snapshot_id": snapshot.snapshot_id, "file_count": len(snapshot.files)},
    )

    if model == "test-placeholder":
        answer = f"【占位】收到请求：{message[:60]}"
        yield f"data: {json.dumps({'type': 'delta', 'text': answer})}\n\n"
        llm_info = {"model": "test-placeholder"}
    else:
        try:
            import asyncio
            import threading
            from app.agent.s_full import agent_loop, switch_workspace_root

            switch_workspace_root(str(get_workspace_root()))
            
            q = asyncio.Queue()
            loop = asyncio.get_running_loop()
            
            def run_agent():
                try:
                    for chunk in agent_loop(history, request_id):
                        loop.call_soon_threadsafe(q.put_nowait, {"type": "chunk", "data": chunk})
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "done"})
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "data": str(e)})

            t = threading.Thread(target=run_agent, daemon=True)
            t.start()
            
            while True:
                item = await q.get()
                if item["type"] == "done":
                    break
                elif item["type"] == "error":
                    raise Exception(item["data"])
                elif item["type"] == "chunk":
                    chunk = item["data"]
                    answer += chunk
                    yield f"data: {json.dumps({'type': 'delta', 'text': chunk})}\n\n"
                
            if not answer:
                answer = "(Agent returned empty)"
                yield f"data: {json.dumps({'type': 'delta', 'text': answer})}\n\n"
        except Exception as e:
            answer += f"\n【Agent Error】: {e}"
            llm_info = {"error": str(e)}
            yield f"data: {json.dumps({'type': 'delta', 'text': f'【Agent Error】: {e}'})}\n\n"

    session_store.append_message(session.session_id, "assistant", answer)
    timeline_store.publish(request_id, "parent-agent", "done", {"answer_preview": answer[:30]})
    review = review_store.commit_snapshot(snapshot.snapshot_id)
    timeline_store.publish(
        request_id,
        "review",
        "changes.committed",
        {"review_id": review.review_id, "changed_files": len(review.files)},
    )

    final_result = {
        "request_id": request_id,
        "session_id": session.session_id,
        "answer": answer,
        "llm": llm_info,
        "code_refs": ref_summaries,
        "review": review_store.serialize_review(review),
    }
    yield f"data: {json.dumps({'type': 'done', 'result': final_result})}\n\n"
