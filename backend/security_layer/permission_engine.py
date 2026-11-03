"""Deny-by-default permission engine for the Security & Organization Layer."""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from security_layer.role_service import get_user_permissions
from security_layer.membership_service import validate_membership
from core.database import DocumentACL, OrganizationMember


async def check_permission(
    user_id: int,
    org_id: int,
    permission_key: str,
    db: AsyncSession,
) -> bool:
    """Return True if user has the permission in the org, False otherwise."""
    try:
        perms = await get_user_permissions(user_id, org_id, db)
        return permission_key in perms
    except Exception:
        return False


async def require_permission(
    user_id: int,
    org_id: int,
    permission_key: str,
    db: AsyncSession,
) -> None:
    """Raise 403 if user does not have the required permission."""
    allowed = await check_permission(user_id, org_id, permission_key, db)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission_key}",
        )


async def check_document_access(
    user_id: int,
    org_id: int,
    document_id: int,
    db: AsyncSession,
) -> bool:
    """
    Return True if user is allowed to access the document per its ACL.
    Deny-by-default: if no ACL record exists, deny access.
    """
    result = await db.execute(
        select(DocumentACL).where(
            DocumentACL.document_id == document_id,
            DocumentACL.organization_id == org_id,
        )
    )
    acl = result.scalars().first()
    if not acl:
        return False
    if acl.approval_status in ("rejected", "revoked"):
        return False

    # public classification: any active org member can access
    if acl.classification == "public":
        try:
            await validate_membership(user_id, org_id, db)
            return True
        except HTTPException:
            return False

    # Check explicit user allow-list
    if acl.allowed_user_ids and user_id in acl.allowed_user_ids:
        return True

    # Check role-based access
    if acl.allowed_roles:
        from core.database import OrganizationRole, RoleTemplate
        result2 = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.organization_id == org_id,
                OrganizationMember.is_active == True,
            )
        )
        member = result2.scalars().first()
        if member and member.org_role_id:
            result3 = await db.execute(
                select(OrganizationRole).where(OrganizationRole.id == member.org_role_id)
            )
            org_role = result3.scalars().first()
            if org_role and org_role.template_id:
                result4 = await db.execute(
                    select(RoleTemplate).where(RoleTemplate.id == org_role.template_id)
                )
                template = result4.scalars().first()
                if template and template.role_name in acl.allowed_roles:
                    return True
    return False


async def get_authorized_document_ids(
    user_id: int,
    org_id: int,
    workspace_id: int,
    db: AsyncSession,
) -> list[int]:
    """Return list of document IDs the user is authorized to access in a workspace."""
    from core.database import Document
    result = await db.execute(
        select(Document).where(Document.workspace_id == workspace_id)
    )
    docs = result.scalars().all()
    authorized = []
    for doc in docs:
        if await check_document_access(user_id, org_id, doc.id, db):
            authorized.append(doc.id)
    return authorized
