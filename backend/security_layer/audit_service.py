"""Organization audit logging service."""
from datetime import datetime
from typing import Any, Optional, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import OrgAuditLog


async def log_event(
    org_id: int,
    action: str,
    db: AsyncSession,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> OrgAuditLog:
    entry = OrgAuditLog(
        user_id=user_id,
        organization_id=org_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
    )
    db.add(entry)
    await db.commit()
    return entry


async def get_audit_logs(
    org_id: int,
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> List[OrgAuditLog]:
    result = await db.execute(
        select(OrgAuditLog)
        .where(OrgAuditLog.organization_id == org_id)
        .order_by(OrgAuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
