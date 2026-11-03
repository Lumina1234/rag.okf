"""Role template seeding and role assignment service."""
from datetime import datetime
from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import (
    RoleTemplate, OrganizationRole, UserRoleAssignment,
    Permission, RolePermission, OrganizationMember, Organization,
)

# ── Permission keys ────────────────────────────────────────────────────────────
ALL_PERMISSIONS = [
    ("organization.read",    "View organization details",           "organization"),
    ("organization.manage",  "Create/edit/delete organization",     "organization"),
    ("member.read",          "View member list",                    "member"),
    ("member.invite",        "Invite new members",                  "member"),
    ("member.manage",        "Edit/remove members",                 "member"),
    ("workspace.read",       "View workspaces",                     "workspace"),
    ("workspace.create",     "Create new workspaces",               "workspace"),
    ("workspace.manage",     "Edit/delete workspaces",              "workspace"),
    ("document.read",        "View/download documents",             "document"),
    ("document.upload",      "Upload new documents",                "document"),
    ("document.update",      "Edit document metadata",              "document"),
    ("document.delete",      "Delete documents",                    "document"),
    ("document.approve",     "Approve/reject document ACL",         "document"),
    ("analytics.read",       "Run analytics queries",               "analytics"),
    ("audit.read",           "View audit logs",                     "audit"),
]

# ── Role definitions ───────────────────────────────────────────────────────────
EDUCATION_ROLES = [
    {
        "role_name": "institution_admin",
        "display_name": "Institution Admin",
        "permissions": [p[0] for p in ALL_PERMISSIONS],
    },
    {
        "role_name": "principal",
        "display_name": "Principal",
        "permissions": [
            "organization.read", "member.read", "member.invite",
            "workspace.read", "workspace.create", "workspace.manage",
            "document.read", "document.upload", "document.approve",
            "analytics.read", "audit.read",
        ],
    },
    {
        "role_name": "hod",
        "display_name": "Head of Department",
        "permissions": [
            "organization.read", "member.read", "member.invite",
            "workspace.read", "workspace.create",
            "document.read", "document.upload", "document.approve",
            "analytics.read",
        ],
    },
    {
        "role_name": "faculty",
        "display_name": "Faculty",
        "permissions": [
            "organization.read", "member.read",
            "workspace.read", "workspace.create",
            "document.read", "document.upload",
            "analytics.read",
        ],
    },
    {
        "role_name": "student",
        "display_name": "Student",
        "permissions": [
            "organization.read",
            "workspace.read",
            "document.read",
            "analytics.read",
        ],
    },
    {
        "role_name": "examination_officer",
        "display_name": "Examination Officer",
        "permissions": [
            "organization.read", "member.read",
            "workspace.read", "workspace.create",
            "document.read", "document.upload", "document.approve",
        ],
    },
    {
        "role_name": "librarian",
        "display_name": "Librarian",
        "permissions": [
            "organization.read",
            "workspace.read", "workspace.create",
            "document.read", "document.upload",
        ],
    },
]

BUSINESS_ROLES = [
    {
        "role_name": "company_admin",
        "display_name": "Company Admin",
        "permissions": [p[0] for p in ALL_PERMISSIONS],
    },
    {
        "role_name": "ceo",
        "display_name": "CEO",
        "permissions": [
            "organization.read", "member.read",
            "workspace.read", "workspace.create", "workspace.manage",
            "document.read", "document.upload", "document.approve",
            "analytics.read", "audit.read",
        ],
    },
    {
        "role_name": "hr_manager",
        "display_name": "HR Manager",
        "permissions": [
            "organization.read", "member.read", "member.invite", "member.manage",
            "workspace.read", "workspace.create",
            "document.read", "document.upload",
            "analytics.read",
        ],
    },
    {
        "role_name": "finance_manager",
        "display_name": "Finance Manager",
        "permissions": [
            "organization.read", "member.read",
            "workspace.read", "workspace.create",
            "document.read", "document.upload",
            "analytics.read",
        ],
    },
    {
        "role_name": "marketing_manager",
        "display_name": "Marketing Manager",
        "permissions": [
            "organization.read", "member.read",
            "workspace.read", "workspace.create",
            "document.read", "document.upload",
            "analytics.read",
        ],
    },
    {
        "role_name": "sales_manager",
        "display_name": "Sales Manager",
        "permissions": [
            "organization.read", "member.read",
            "workspace.read", "workspace.create",
            "document.read", "document.upload",
            "analytics.read",
        ],
    },
    {
        "role_name": "employee",
        "display_name": "Employee",
        "permissions": [
            "organization.read",
            "workspace.read",
            "document.read",
            "analytics.read",
        ],
    },
]


async def seed_permissions(db: AsyncSession) -> dict:
    """Idempotently seed the permissions table. Returns {key: Permission} map."""
    perm_map = {}
    for key, desc, cat in ALL_PERMISSIONS:
        result = await db.execute(select(Permission).where(Permission.permission_key == key))
        perm = result.scalars().first()
        if not perm:
            perm = Permission(permission_key=key, description=desc, category=cat)
            db.add(perm)
            await db.flush()
        perm_map[key] = perm
    return perm_map


async def seed_role_templates(db: AsyncSession) -> None:
    """Idempotently create all 14 role templates (7 edu + 7 biz)."""
    perm_map = await seed_permissions(db)
    all_roles = [
        ("education", EDUCATION_ROLES),
        ("business", BUSINESS_ROLES),
    ]
    for portal_type, roles in all_roles:
        for role_def in roles:
            result = await db.execute(
                select(RoleTemplate).where(
                    RoleTemplate.portal_type == portal_type,
                    RoleTemplate.role_name == role_def["role_name"],
                )
            )
            existing = result.scalars().first()
            if not existing:
                tmpl = RoleTemplate(
                    portal_type=portal_type,
                    role_name=role_def["role_name"],
                    display_name=role_def["display_name"],
                    default_permissions=role_def["permissions"],
                )
                db.add(tmpl)
    await db.commit()


async def get_user_permissions(user_id: int, organization_id: int, db: AsyncSession) -> Set[str]:
    """Return the set of permission keys the user has in the given organization."""
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.is_active == True,
        )
    )
    member = result.scalars().first()
    if not member or not member.org_role_id:
        return set()

    result = await db.execute(
        select(OrganizationRole).where(OrganizationRole.id == member.org_role_id)
    )
    org_role = result.scalars().first()
    if not org_role:
        return set()

    perms: Set[str] = set()

    if org_role.template_id:
        result2 = await db.execute(
            select(RoleTemplate).where(RoleTemplate.id == org_role.template_id)
        )
        template = result2.scalars().first()
        if template and template.default_permissions:
            perms.update(template.default_permissions)

    if org_role.custom_permissions:
        perms.update(org_role.custom_permissions)

    return perms


async def assign_role(
    user_id: int,
    organization_id: int,
    role_id: int,
    assigned_by: int,
    db: AsyncSession,
) -> UserRoleAssignment:
    """Assign an OrganizationRole to a user."""
    assignment = UserRoleAssignment(
        user_id=user_id,
        organization_id=organization_id,
        role_id=role_id,
        assigned_by=assigned_by,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment
