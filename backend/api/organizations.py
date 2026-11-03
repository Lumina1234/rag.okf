"""Organization management API routes."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import CurrentUser, DBSession, AdminUser
from core.database import (
    Organization, Department, OrganizationMember, OrganizationRole,
    RoleTemplate, OrgWorkspace, Workspace, DocumentACL, OrgAuditLog,
    User,
)
from security_layer.organization_service import (
    create_organization, get_organization, list_user_organizations,
    create_department, list_departments,
)
from security_layer.membership_service import (
    validate_membership, add_member, remove_member,
)
from security_layer.permission_engine import (
    check_permission, require_permission, check_document_access,
)
from security_layer.workspace_service import (
    get_org_workspaces, create_org_workspace, link_workspace_to_org,
)
from security_layer.document_acl_service import (
    approve_document, revoke_document, update_acl, get_acl,
)
from security_layer.audit_service import get_audit_logs, log_event
from security_layer.role_service import get_user_permissions

router = APIRouter(tags=["organizations"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class CreateOrgRequest(BaseModel):
    name: str
    org_type: str  # education | business
    settings_data: Optional[Dict[str, Any]] = None


class CreateDepartmentRequest(BaseModel):
    name: str
    dept_type: Optional[str] = None
    parent_id: Optional[int] = None


class AddMemberRequest(BaseModel):
    user_id: int
    role_id: int
    department_id: Optional[int] = None


class CreateWorkspaceRequest(BaseModel):
    name: str
    workspace_type: str = "business"


class UpdateACLRequest(BaseModel):
    classification: Optional[str] = None
    allowed_roles: Optional[List[str]] = None
    allowed_user_ids: Optional[List[int]] = None


class CheckPermissionRequest(BaseModel):
    organization_id: int
    permission_key: str


# ── Organization endpoints ─────────────────────────────────────────────────────

@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_org(
    body: CreateOrgRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Platform admin creates a new organization."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    org = await create_organization(
        name=body.name,
        org_type=body.org_type,
        admin_user_id=current_user.id,
        db=db,
        settings_data=body.settings_data,
    )
    from security_layer.tenant_storage_service import create_org_storage_dirs
    create_org_storage_dirs(org.id, org.org_type)
    return {"id": org.id, "name": org.name, "org_type": org.org_type, "slug": org.slug}


@router.get("/organizations")
async def list_orgs(current_user: CurrentUser, db: DBSession):
    """List organizations the current user belongs to."""
    orgs = await list_user_organizations(current_user.id, db)
    return [{"id": o.id, "name": o.name, "org_type": o.org_type, "slug": o.slug} for o in orgs]


@router.get("/organizations/{org_id}")
async def get_org(org_id: int, current_user: CurrentUser, db: DBSession):
    await validate_membership(current_user.id, org_id, db)
    org = await get_organization(org_id, db)
    return {
        "id": org.id, "name": org.name, "org_type": org.org_type,
        "slug": org.slug, "is_active": org.is_active,
        "settings": org.settings_data, "created_at": str(org.created_at),
    }


# ── Department endpoints ───────────────────────────────────────────────────────

@router.post("/organizations/{org_id}/departments", status_code=201)
async def create_dept(
    org_id: int, body: CreateDepartmentRequest,
    current_user: CurrentUser, db: DBSession,
):
    await validate_membership(current_user.id, org_id, db)
    await require_permission(current_user.id, org_id, "organization.manage", db)
    dept = await create_department(org_id, body.name, db, body.dept_type, body.parent_id)
    return {"id": dept.id, "name": dept.name, "org_id": org_id}


@router.get("/organizations/{org_id}/departments")
async def list_depts(org_id: int, current_user: CurrentUser, db: DBSession):
    await validate_membership(current_user.id, org_id, db)
    depts = await list_departments(org_id, db)
    return [{"id": d.id, "name": d.name, "dept_type": d.dept_type, "parent_id": d.parent_id} for d in depts]


# ── Member endpoints ───────────────────────────────────────────────────────────

@router.post("/organizations/{org_id}/members", status_code=201)
async def add_org_member(
    org_id: int, body: AddMemberRequest,
    current_user: CurrentUser, db: DBSession,
):
    await validate_membership(current_user.id, org_id, db)
    await require_permission(current_user.id, org_id, "member.invite", db)
    member = await add_member(body.user_id, org_id, body.role_id, db, body.department_id)
    await log_event(org_id, "member.add", db, current_user.id, "member", str(body.user_id))
    return {"id": member.id, "user_id": member.user_id, "org_id": org_id}


@router.get("/organizations/{org_id}/members")
async def list_org_members(org_id: int, current_user: CurrentUser, db: DBSession):
    await validate_membership(current_user.id, org_id, db)
    await require_permission(current_user.id, org_id, "member.read", db)
    result = await db.execute(
        select(OrganizationMember).where(OrganizationMember.organization_id == org_id)
    )
    members = result.scalars().all()
    return [
        {"id": m.id, "user_id": m.user_id, "org_role_id": m.org_role_id,
         "department_id": m.department_id, "is_active": m.is_active}
        for m in members
    ]


@router.delete("/organizations/{org_id}/members/{user_id}", status_code=200)
async def remove_org_member(
    org_id: int, user_id: int,
    current_user: CurrentUser, db: DBSession,
):
    await validate_membership(current_user.id, org_id, db)
    await require_permission(current_user.id, org_id, "member.manage", db)
    await remove_member(user_id, org_id, db)
    return {"status": "removed"}


# ── Workspace endpoints ────────────────────────────────────────────────────────

@router.post("/organizations/{org_id}/workspaces", status_code=201)
async def create_org_ws(
    org_id: int, body: CreateWorkspaceRequest,
    current_user: CurrentUser, db: DBSession,
):
    await validate_membership(current_user.id, org_id, db)
    await require_permission(current_user.id, org_id, "workspace.create", db)
    ws = await create_org_workspace(org_id, body.name, body.workspace_type, current_user.id, db)
    return {"id": ws.id, "name": ws.name, "workspace_type": ws.workspace_type}


@router.get("/organizations/{org_id}/workspaces")
async def list_org_ws(org_id: int, current_user: CurrentUser, db: DBSession):
    await validate_membership(current_user.id, org_id, db)
    await require_permission(current_user.id, org_id, "workspace.read", db)
    workspaces = await get_org_workspaces(org_id, db)
    return [{"id": ws.id, "name": ws.name, "workspace_type": ws.workspace_type} for ws in workspaces]


# ── Role endpoints ─────────────────────────────────────────────────────────────

@router.get("/roles")
async def list_role_templates(current_user: CurrentUser, db: DBSession):
    result = await db.execute(select(RoleTemplate))
    templates = result.scalars().all()
    return [
        {"id": t.id, "portal_type": t.portal_type, "role_name": t.role_name,
         "display_name": t.display_name, "permissions": t.default_permissions}
        for t in templates
    ]


# ── Permission check endpoint ─────────────────────────────────────────────────

@router.post("/permissions/check")
async def check_perm(body: CheckPermissionRequest, current_user: CurrentUser, db: DBSession):
    allowed = await check_permission(current_user.id, body.organization_id, body.permission_key, db)
    return {"allowed": allowed, "permission": body.permission_key}


# ── Document ACL endpoints ────────────────────────────────────────────────────

@router.put("/documents/{doc_id}/acl")
async def update_doc_acl(
    doc_id: int, body: UpdateACLRequest,
    current_user: CurrentUser, db: DBSession,
):
    from core.database import Document
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result3 = await db.execute(
        select(OrgWorkspace).where(OrgWorkspace.workspace_id == doc.workspace_id)
    )
    ow = result3.scalars().first()
    if not ow:
        raise HTTPException(status_code=403, detail="Document not associated with any organization")

    await validate_membership(current_user.id, ow.organization_id, db)
    await require_permission(current_user.id, ow.organization_id, "document.approve", db)

    acl = await update_acl(doc_id, ow.organization_id, db, body.classification, body.allowed_roles, body.allowed_user_ids)
    return {"document_id": doc_id, "classification": acl.classification, "approval_status": acl.approval_status}


@router.post("/documents/{doc_id}/approve")
async def approve_doc(doc_id: int, current_user: CurrentUser, db: DBSession):
    from core.database import Document
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result3 = await db.execute(select(OrgWorkspace).where(OrgWorkspace.workspace_id == doc.workspace_id))
    ow = result3.scalars().first()
    if not ow:
        raise HTTPException(status_code=403, detail="Not in any organization")

    await validate_membership(current_user.id, ow.organization_id, db)
    await require_permission(current_user.id, ow.organization_id, "document.approve", db)

    acl = await approve_document(doc_id, ow.organization_id, current_user.id, db)
    return {"document_id": doc_id, "approval_status": acl.approval_status}


@router.post("/documents/{doc_id}/revoke")
async def revoke_doc(doc_id: int, current_user: CurrentUser, db: DBSession):
    from core.database import Document
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result3 = await db.execute(select(OrgWorkspace).where(OrgWorkspace.workspace_id == doc.workspace_id))
    ow = result3.scalars().first()
    if not ow:
        raise HTTPException(status_code=403, detail="Not in any organization")

    await validate_membership(current_user.id, ow.organization_id, db)
    await require_permission(current_user.id, ow.organization_id, "document.approve", db)

    acl = await revoke_document(doc_id, ow.organization_id, db)
    return {"document_id": doc_id, "approval_status": acl.approval_status}


# ── Audit log endpoint ────────────────────────────────────────────────────────

@router.get("/security/audit-logs")
async def audit_logs(
    org_id: int, current_user: CurrentUser, db: DBSession,
    limit: int = 100, offset: int = 0,
):
    await validate_membership(current_user.id, org_id, db)
    await require_permission(current_user.id, org_id, "audit.read", db)
    logs = await get_audit_logs(org_id, db, limit, offset)
    return [
        {
            "id": l.id, "user_id": l.user_id, "action": l.action,
            "resource_type": l.resource_type, "resource_id": l.resource_id,
            "created_at": str(l.created_at),
        }
        for l in logs
    ]
