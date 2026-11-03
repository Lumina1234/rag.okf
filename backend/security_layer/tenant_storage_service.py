"""Tenant-isolated storage path management and FAISS index registry."""
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import RAGIndexRegistry


def get_org_index_path(org_id: int, org_type: str, workspace_id: int) -> Path:
    """
    Return the filesystem path for the org's FAISS index.
    Path: backend/vector_db/{edu|biz}/{org_id}/{workspace_id}/faiss_index/
    Never trust client-supplied paths.
    """
    prefix = "edu" if org_type == "education" else "biz"
    return settings.VECTOR_DB_DIR / prefix / str(org_id) / str(workspace_id) / "faiss_index"


def create_org_storage_dirs(org_id: int, org_type: str) -> None:
    """Create isolated storage directories for the organization."""
    prefix = "edu" if org_type == "education" else "biz"
    base = settings.ORG_STORAGE_DIR / prefix / str(org_id)
    for subdir in ("documents", "indexes", "exports"):
        (base / subdir).mkdir(parents=True, exist_ok=True)


async def register_index(
    org_id: int,
    workspace_id: int,
    index_path: Path,
    db: AsyncSession,
) -> RAGIndexRegistry:
    """Register or update a FAISS index in the registry."""
    result = await db.execute(
        select(RAGIndexRegistry).where(
            RAGIndexRegistry.organization_id == org_id,
            RAGIndexRegistry.workspace_id == workspace_id,
        )
    )
    existing = result.scalars().first()
    if existing:
        existing.index_path = str(index_path)
        existing.last_updated = datetime.utcnow()
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return existing

    entry = RAGIndexRegistry(
        organization_id=org_id,
        workspace_id=workspace_id,
        index_path=str(index_path),
        last_updated=datetime.utcnow(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_index_path_from_registry(
    org_id: int,
    workspace_id: int,
    db: AsyncSession,
) -> Optional[Path]:
    """Look up the FAISS index path from the registry (never from client input)."""
    result = await db.execute(
        select(RAGIndexRegistry).where(
            RAGIndexRegistry.organization_id == org_id,
            RAGIndexRegistry.workspace_id == workspace_id,
            RAGIndexRegistry.is_active == True,
        )
    )
    entry = result.scalars().first()
    if not entry:
        return None
    return Path(entry.index_path)
