"""
Chat API routes — RAG query with streaming.
POST /chat/query       - streaming RAG answer
GET  /chat/history     - chat message history for a workspace
POST /chat/clear       - clear chat history
"""
import json
import logging
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete

from core.database import AuditLog, ChatMessage, Workspace, AsyncSessionLocal
from core.deps import CurrentUser, DBSession
from core.config import settings
from models.schemas import ChatMessageResponse, ChatRequest
from services import rag_engine
from services.harness import default_privacy_guard

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


@router.post("/query")
async def query(payload: ChatRequest, current_user: CurrentUser, db: DBSession):
    """
    Streaming RAG endpoint.
    Streams:
      1. A JSON line: {"type":"sources","data":[...]}
      2. Plain text tokens from the LLM
    """
    # Validate workspace ownership
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == payload.workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = ws_result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Fetch recent messages for conversational context resolution
    recent_res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.workspace_id == payload.workspace_id, ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(4)
    )
    recent_msgs = list(reversed([{"role": m.role, "content": m.content} for m in recent_res.scalars().all()]))

    # Save user message
    user_msg = ChatMessage(
        workspace_id=payload.workspace_id,
        user_id=current_user.id,
        role="user",
        content=payload.question,
        chat_type="workspace",
    )
    db.add(user_msg)
    await db.commit()

    # Enforce strict workspace isolation - search the authorized workspace
    workspace_ids = [payload.workspace_id]

    async def event_stream():
        collected_answer = []
        sources_data = []

        async for chunk in rag_engine.rag_stream(
            question=payload.question,
            workspace_id=workspace_ids,
            workspace_type=workspace.workspace_type,
            model=payload.model,
            chat_history=recent_msgs,
        ):
            raw_chunk = chunk.strip()
            if raw_chunk.startswith('{"type"'):
                try:
                    parsed = json.loads(raw_chunk)
                    if parsed.get("type") == "sources":
                        sources_data = parsed.get("data", [])
                    yield chunk
                except Exception:
                    yield chunk
                continue

            collected_answer.append(chunk)
            yield chunk

        # Persist assistant message after streaming completes
        raw_answer = "".join(collected_answer)
        clean_ans = re.sub(r'^[,\s]*\{"type":\s*"sources"[^\r\n]*', '', raw_answer)
        clean_ans = re.sub(r'^[,\s]*\{"type":\s*"trace"[^\r\n]*', '', clean_ans)
        clean_ans = re.sub(r'^\s*Question:.*?\bAnswer:\s*', '', clean_ans, flags=re.DOTALL)
        clean_ans = re.sub(r'^\s*Answer:\s*', '', clean_ans, flags=re.IGNORECASE)
        clean_ans = default_privacy_guard.sanitize_output(clean_ans)
        clean_ans = clean_ans.strip()

        try:
            async with AsyncSessionLocal() as save_db:
                save_db.add(ChatMessage(
                    workspace_id=payload.workspace_id,
                    user_id=current_user.id,
                    role="assistant",
                    content=clean_ans or raw_answer.strip(),
                    sources=sources_data,
                    chat_type="workspace",
                ))
                save_db.add(AuditLog(
                    user_id=current_user.id,
                    action="chat_query",
                    resource="chat",
                    details={
                        "workspace_id": payload.workspace_id,
                        "question": payload.question[:500],
                        "model": payload.model or settings.DEFAULT_LLM_MODEL,
                    },
                ))
                await save_db.commit()
        except Exception as e:
            logger.error(f"Failed to persist assistant chat message: {e}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history", response_model=list[ChatMessageResponse])
async def get_history(
    workspace_id: int,
    current_user: CurrentUser,
    db: DBSession,
    limit: int = 500,
    chat_type: str = "workspace",
):
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    filters = [
        ChatMessage.workspace_id == workspace_id,
        ChatMessage.user_id == current_user.id,
    ]
    if chat_type and chat_type != "all":
        filters.append(ChatMessage.chat_type == chat_type)

    # Fetch the most recent messages up to limit, returned in chronological order
    result = await db.execute(
        select(ChatMessage)
        .where(*filters)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


@router.post("/clear", status_code=204)
async def clear_history(
    workspace_id: int,
    current_user: CurrentUser,
    db: DBSession,
    chat_type: str = "workspace",
):
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    filters = [
        ChatMessage.workspace_id == workspace_id,
        ChatMessage.user_id == current_user.id,
    ]
    if chat_type and chat_type != "all":
        filters.append(ChatMessage.chat_type == chat_type)

    await db.execute(delete(ChatMessage).where(*filters))
    await db.commit()
