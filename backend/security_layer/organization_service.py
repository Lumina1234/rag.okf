"""Organization creation and management service."""
import re
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import (
    Organization, Department, OrganizationRole, OrganizationMember,
    RoleTemplate, User,
)
from security_layer.membership_service import add_member


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "org"


async def create_organization(
    name: str,
    org_type: str,
    admin_user_id: int,
    db: AsyncSession,
    settings_data: dict | None = None,
) -> Organization:
    """Create a new organization and assign the creator as its admin."""
    if org_type not in ("education", "business"):
        raise HTTPException(status_code=400, detail="org_type must be 'education' or 'business'")

    slug_base = _slugify(name)
    slug = slug_base
    counter = 1
    while True:
        result = await db.execute(select(Organization).where(Organization.slug == slug))
        if not result.scalars().first():
            break
        slug = f"{slug_base}-{counter}"
        counter += 1

    org = Organization(
        name=name,
        org_type=org_type,
        slug=slug,
        is_active=True,
        settings_data=settings_data or {},
    )
    db.add(org)
    await db.flush()  # get org.id

    # Find the admin role template for this portal
    admin_role_name = "institution_admin" if org_type == "education" else "company_admin"
    result = await db.execute(
        select(RoleTemplate).where(
            RoleTemplate.portal_type == org_type,
            RoleTemplate.role_name == admin_role_name,
        )
    )
    template = result.scalars().first()

    # Create an OrganizationRole for this org based on template
    org_role = OrganizationRole(
        organization_id=org.id,
        template_id=template.id if template else None,
        custom_permissions=None,
    )
    db.add(org_role)
    await db.flush()

    # Add admin user as member with admin role
    member = OrganizationMember(
        user_id=admin_user_id,
        organization_id=org.id,
        org_role_id=org_role.id,
        is_active=True,
    )
    db.add(member)
    await db.commit()
    await db.refresh(org)
    return org


async def get_organization(org_id: int, db: AsyncSession) -> Organization:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalars().first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def list_user_organizations(user_id: int, db: AsyncSession) -> list[Organization]:
    """Return all organizations the user is an active member of."""
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active == True,
            Organization.is_active == True,
        )
    )
    return list(result.scalars().all())


async def create_department(
    org_id: int,
    name: str,
    db: AsyncSession,
    dept_type: str | None = None,
    parent_id: int | None = None,
) -> Department:
    dept = Department(
        organization_id=org_id,
        name=name,
        dept_type=dept_type,
        parent_id=parent_id,
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


async def list_departments(org_id: int, db: AsyncSession) -> list[Department]:
    result = await db.execute(
        select(Department).where(Department.organization_id == org_id)
    )
    return list(result.scalars().all())
