"""Organization membership validation service."""
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import OrganizationMember, Organization


async def get_membership(user_id: int, org_id: int, db: AsyncSession) -> Optional[OrganizationMember]:
    """Return the membership record, or None if not found."""
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == org_id,
        )
    )
    return result.scalars().first()


async def validate_membership(user_id: int, org_id: int, db: AsyncSession) -> OrganizationMember:
    """Raise 403 if user is not an active member of the organization."""
    member = await get_membership(user_id, org_id, db)
    if not member or not member.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an active member of this organization.",
        )
    return member


async def add_member(
    user_id: int,
    org_id: int,
    role_id: int,
    db: AsyncSession,
    department_id: Optional[int] = None,
) -> OrganizationMember:
    """Add a user as an active member of the organization."""
    existing = await get_membership(user_id, org_id, db)
    if existing:
        existing.is_active = True
        existing.org_role_id = role_id
        if department_id is not None:
            existing.department_id = department_id
        await db.commit()
        await db.refresh(existing)
        return existing

    member = OrganizationMember(
        user_id=user_id,
        organization_id=org_id,
        org_role_id=role_id,
        department_id=department_id,
        is_active=True,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def remove_member(user_id: int, org_id: int, db: AsyncSession) -> None:
    """Deactivate a member (soft delete)."""
    member = await get_membership(user_id, org_id, db)
    if member:
        member.is_active = False
        await db.commit()
