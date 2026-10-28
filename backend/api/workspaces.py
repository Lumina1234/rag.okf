"""
Workspace API routes.
GET    /workspaces/          - list current user's workspaces
POST   /workspaces/          - create workspace
GET    /workspaces/{id}      - get workspace details
DELETE /workspaces/{id}      - delete workspace
"""
import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from core.database import Document, Workspace
from core.deps import CurrentUser, DBSession
from models.schemas import WorkspaceCreate, WorkspaceResponse

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])
logger = logging.getLogger(__name__)


async def _get_workspace_or_404(ws_id: int, user_id: int, db) -> Workspace:
    result = await db.execute(
        select(Workspace).where(Workspace.id == ws_id, Workspace.owner_id == user_id)
    )
    ws = result.scalars().first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.get("/", response_model=list[WorkspaceResponse])
async def list_workspaces(current_user: CurrentUser, db: DBSession):
    result = await db.execute(
        select(Workspace).where(Workspace.owner_id == current_user.id).order_by(Workspace.created_at.desc())
    )
    workspaces = result.scalars().all()

    # Attach document counts
    responses = []
    for ws in workspaces:
        count_result = await db.execute(
            select(func.count(Document.id)).where(Document.workspace_id == ws.id)
        )
        count = count_result.scalar() or 0
        r = WorkspaceResponse.model_validate(ws)
        r.document_count = count
        responses.append(r)

    return responses


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(payload: WorkspaceCreate, current_user: CurrentUser, db: DBSession):
    ws = Workspace(
        name=payload.name,
        workspace_type=payload.workspace_type,
        description=payload.description,
        owner_id=current_user.id,
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    logger.info(f"Created workspace '{ws.name}' for user {current_user.id}")
    r = WorkspaceResponse.model_validate(ws)
    r.document_count = 0
    return r


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(workspace_id: int, current_user: CurrentUser, db: DBSession):
    ws = await _get_workspace_or_404(workspace_id, current_user.id, db)
    count_result = await db.execute(
        select(func.count(Document.id)).where(Document.workspace_id == ws.id)
    )
    r = WorkspaceResponse.model_validate(ws)
    r.document_count = count_result.scalar() or 0
    return r


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: int, current_user: CurrentUser, db: DBSession):
    ws = await _get_workspace_or_404(workspace_id, current_user.id, db)
    await db.delete(ws)
    await db.commit()

    # Clean up FAISS index
    import shutil
    from core.config import settings
    idx_dir = settings.VECTOR_DB_DIR / str(workspace_id)
    if idx_dir.exists():
        shutil.rmtree(idx_dir)
    from services.vector_store import invalidate_cache
    invalidate_cache(workspace_id)
    logger.info(f"Deleted workspace {workspace_id}")
