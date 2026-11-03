"""Workspace resolution and org-workspace binding service."""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import OrgWorkspace, Workspace, Organization


async def resolve_workspace(
    workspace_id: int,
    org_id: int,
    db: AsyncSession,
) -> Workspace:
    """Validate that workspace_id belongs to org_id. Raises 403 otherwise."""
    result = await db.execute(
        select(OrgWorkspace).where(
            OrgWorkspace.workspace_id == workspace_id,
            OrgWorkspace.organization_id == org_id,
        )
    )
    link = result.scalars().first()
    if not link:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace does not belong to this organization.",
        )
    result2 = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result2.scalars().first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


async def get_org_workspaces(org_id: int, db: AsyncSession) -> list[Workspace]:
    result = await db.execute(
        select(Workspace)
        .join(OrgWorkspace, OrgWorkspace.workspace_id == Workspace.id)
        .where(OrgWorkspace.organization_id == org_id)
    )
    return list(result.scalars().all())


async def create_org_workspace(
    org_id: int,
    name: str,
    workspace_type: str,
    owner_id: int,
    db: AsyncSession,
) -> Workspace:
    ws = Workspace(name=name, workspace_type=workspace_type, owner_id=owner_id)
    db.add(ws)
    await db.flush()

    link = OrgWorkspace(organization_id=org_id, workspace_id=ws.id, is_public_in_org=False)
    db.add(link)
    await db.commit()
    await db.refresh(ws)
    return ws


async def link_workspace_to_org(
    workspace_id: int,
    org_id: int,
    db: AsyncSession,
    is_public: bool = False,
) -> OrgWorkspace:
    """Link an existing workspace to an organization."""
    existing = await db.execute(
        select(OrgWorkspace).where(
            OrgWorkspace.workspace_id == workspace_id,
            OrgWorkspace.organization_id == org_id,
        )
    )
    link = existing.scalars().first()
    if link:
        return link
    link = OrgWorkspace(organization_id=org_id, workspace_id=workspace_id, is_public_in_org=is_public)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link
