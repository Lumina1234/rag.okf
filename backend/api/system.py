"""
System API routes.
GET  /system/status             - Ollama health, model list, DB stats
GET  /system/models             - list available Ollama models
GET  /system/admin/history      - admin-only audit + conversation history
POST /system/download-embedding - pre-download BGE-M3 model (admin)
"""
import logging

from fastapi import APIRouter
from sqlalchemy import func, select

from core.config import settings
from core.database import AuditLog, ChatMessage, Document, User, Workspace
from core.deps import AdminUser, CurrentUser, DBSession
from models.schemas import AdminAuditLogItem, AdminConversationItem, AdminHistoryResponse, SystemStatus
from services import ollama_client

router = APIRouter(prefix="/system", tags=["System"])
logger = logging.getLogger(__name__)


@router.get("/status", response_model=SystemStatus)
async def system_status(current_user: CurrentUser, db: DBSession):
    online = await ollama_client.is_ollama_online()
    models = await ollama_client.list_models() if online else []

    doc_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    ws_count = (await db.execute(
        select(func.count(Workspace.id)).where(Workspace.owner_id == current_user.id)
    )).scalar() or 0

    return SystemStatus(
        ollama_online=online,
        available_models=models,
        embedding_model=settings.EMBEDDING_MODEL,
        default_llm=settings.DEFAULT_LLM_MODEL,
        total_documents=doc_count,
        total_workspaces=ws_count,
        version=settings.APP_VERSION,
    )


@router.get("/models", response_model=list[str])
async def list_models(current_user: CurrentUser):
    """Return names of all locally available Ollama models."""
    return await ollama_client.list_models()


@router.get("/admin/history", response_model=AdminHistoryResponse)
async def admin_history(current_user: AdminUser, db: DBSession):
    """Return admin-only login audit history and all chat conversation history."""
    audit_result = await db.execute(
        select(
            AuditLog.id,
            AuditLog.user_id,
            User.username,
            User.role,
            AuditLog.action,
            AuditLog.resource,
            AuditLog.details,
            AuditLog.created_at,
        )
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.action.in_(["login", "register"]))
        .order_by(AuditLog.created_at.desc())
    )

    login_history = [
        AdminAuditLogItem(**entry)
        for entry in audit_result.mappings().all()
    ]

    conversation_result = await db.execute(
        select(
            ChatMessage.id,
            ChatMessage.workspace_id,
            Workspace.name.label("workspace_name"),
            ChatMessage.user_id,
            User.username,
            User.role.label("user_role"),
            ChatMessage.role,
            ChatMessage.content,
            ChatMessage.sources,
            ChatMessage.created_at,
        )
        .join(Workspace, Workspace.id == ChatMessage.workspace_id)
        .join(User, User.id == ChatMessage.user_id)
        .order_by(ChatMessage.created_at.asc())
    )

    conversation_history = [
        AdminConversationItem(**entry)
        for entry in conversation_result.mappings().all()
    ]

    return AdminHistoryResponse(
        login_history=login_history,
        conversation_history=conversation_history,
    )


@router.post("/download-embedding")
async def download_embedding(current_user: AdminUser):
    """Pre-download the BGE-M3 embedding model for offline use (admin only)."""
    from services.embeddings import embedding_service
    success = embedding_service.download_model()
    if success:
        return {"status": "success", "message": "BGE-M3 model downloaded successfully."}
    return {"status": "error", "message": "Download failed. Check logs for details."}
