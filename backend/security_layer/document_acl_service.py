"""Document ACL management service."""
from datetime import datetime
from typing import Optional, List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import DocumentACL, Document


async def create_acl(
    document_id: int,
    org_id: int,
    db: AsyncSession,
    classification: str = "organization",
    allowed_roles: Optional[List[str]] = None,
    allowed_user_ids: Optional[List[int]] = None,
) -> DocumentACL:
    """Create an ACL record for a document."""
    acl = DocumentACL(
        document_id=document_id,
        organization_id=org_id,
        classification=classification,
        allowed_roles=allowed_roles or [],
        allowed_user_ids=allowed_user_ids or [],
        approval_status="draft",
    )
    db.add(acl)
    await db.commit()
    await db.refresh(acl)
    return acl


async def get_acl(document_id: int, org_id: int, db: AsyncSession) -> Optional[DocumentACL]:
    result = await db.execute(
        select(DocumentACL).where(
            DocumentACL.document_id == document_id,
            DocumentACL.organization_id == org_id,
        )
    )
    return result.scalars().first()


async def update_acl(
    document_id: int,
    org_id: int,
    db: AsyncSession,
    classification: Optional[str] = None,
    allowed_roles: Optional[List[str]] = None,
    allowed_user_ids: Optional[List[int]] = None,
) -> DocumentACL:
    acl = await get_acl(document_id, org_id, db)
    if not acl:
        raise HTTPException(status_code=404, detail="ACL record not found")
    if classification is not None:
        acl.classification = classification
    if allowed_roles is not None:
        acl.allowed_roles = allowed_roles
    if allowed_user_ids is not None:
        acl.allowed_user_ids = allowed_user_ids
    await db.commit()
    await db.refresh(acl)
    return acl


async def approve_document(document_id: int, org_id: int, approver_id: int, db: AsyncSession) -> DocumentACL:
    acl = await get_acl(document_id, org_id, db)
    if not acl:
        raise HTTPException(status_code=404, detail="ACL record not found")
    acl.approval_status = "approved"
    acl.approved_by = approver_id
    acl.approved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(acl)
    return acl


async def revoke_document(document_id: int, org_id: int, db: AsyncSession) -> DocumentACL:
    """Immediately revoke document access (blocks retrieval; async vector cleanup is separate)."""
    acl = await get_acl(document_id, org_id, db)
    if not acl:
        raise HTTPException(status_code=404, detail="ACL record not found")
    acl.approval_status = "revoked"
    await db.commit()
    await db.refresh(acl)
    return acl
