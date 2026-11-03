"""
Security & Organization Layer — Acceptance and Regression Tests
Validates: membership, permissions, document ACL, cross-org isolation, existing RAG regression.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from core.database import Base


# ── In-memory async SQLite test engine ────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="function")
async def db():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _create_user(db, username="testuser", role="user"):
    from core.database import User
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        username=username,
        email=f"{username}@test.com",
        full_name=username,
        hashed_password=pwd_context.hash("password"),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_org_with_admin(db, name="TestOrg", org_type="business"):
    from security_layer.role_service import seed_role_templates
    await seed_role_templates(db)
    admin = await _create_user(db, username=f"admin_{name.lower().replace(' ', '_')}", role="admin")
    from security_layer.organization_service import create_organization
    org = await create_organization(name=name, org_type=org_type, admin_user_id=admin.id, db=db)
    return org, admin


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestMembershipValidation:

    @pytest.mark.asyncio
    async def test_active_member_passes(self, db):
        """An active member should pass membership validation."""
        org, admin = await _create_org_with_admin(db, "OrgA", "business")
        from security_layer.membership_service import validate_membership
        member = await validate_membership(admin.id, org.id, db)
        assert member is not None

    @pytest.mark.asyncio
    async def test_non_member_raises_403(self, db):
        """A user not in the org should get 403."""
        org, admin = await _create_org_with_admin(db, "OrgB", "business")
        outsider = await _create_user(db, "outsider")
        from security_layer.membership_service import validate_membership
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await validate_membership(outsider.id, org.id, db)
        assert exc_info.value.status_code == 403


class TestPermissionEngine:

    @pytest.mark.asyncio
    async def test_admin_has_all_permissions(self, db):
        """Company admin should have all permissions."""
        org, admin = await _create_org_with_admin(db, "PermOrg", "business")
        from security_layer.role_service import get_user_permissions
        perms = await get_user_permissions(admin.id, org.id, db)
        assert "document.approve" in perms
        assert "audit.read" in perms
        assert "member.manage" in perms

    @pytest.mark.asyncio
    async def test_deny_by_default_no_membership(self, db):
        """User without membership has no permissions."""
        org, _ = await _create_org_with_admin(db, "DenyOrg", "education")
        outsider = await _create_user(db, "perm_outsider")
        from security_layer.permission_engine import check_permission
        allowed = await check_permission(outsider.id, org.id, "document.read", db)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_require_permission_raises_403(self, db):
        """require_permission raises 403 when denied."""
        org, _ = await _create_org_with_admin(db, "ReqPerm", "business")
        outsider = await _create_user(db, "req_outsider")
        from security_layer.permission_engine import require_permission
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await require_permission(outsider.id, org.id, "workspace.read", db)
        assert exc_info.value.status_code == 403


class TestDocumentACL:

    @pytest.mark.asyncio
    async def test_no_acl_denies_access(self, db):
        """Document with no ACL record must be denied (deny-by-default)."""
        org, admin = await _create_org_with_admin(db, "ACLOrg", "business")
        from security_layer.permission_engine import check_document_access
        allowed = await check_document_access(admin.id, org.id, 999, db)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_revoked_document_denied(self, db):
        """A revoked document must not be accessible."""
        from core.database import Workspace, Document, DocumentACL
        org, admin = await _create_org_with_admin(db, "RevokeOrg", "business")
        ws = Workspace(name="ws", workspace_type="business", owner_id=admin.id)
        db.add(ws)
        await db.flush()
        doc = Document(
            filename="test.pdf", original_filename="test.pdf",
            file_type="pdf", workspace_id=ws.id,
        )
        db.add(doc)
        await db.flush()

        acl = DocumentACL(
            document_id=doc.id, organization_id=org.id,
            classification="organization", approval_status="revoked",
        )
        db.add(acl)
        await db.commit()

        from security_layer.permission_engine import check_document_access
        allowed = await check_document_access(admin.id, org.id, doc.id, db)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_approved_public_document_accessible(self, db):
        """An approved public document should be accessible to any org member."""
        from core.database import Workspace, Document, DocumentACL
        org, admin = await _create_org_with_admin(db, "PublicACLOrg", "business")
        ws = Workspace(name="ws2", workspace_type="business", owner_id=admin.id)
        db.add(ws)
        await db.flush()
        doc = Document(
            filename="pub.pdf", original_filename="pub.pdf",
            file_type="pdf", workspace_id=ws.id,
        )
        db.add(doc)
        await db.flush()

        acl = DocumentACL(
            document_id=doc.id, organization_id=org.id,
            classification="public", approval_status="approved",
        )
        db.add(acl)
        await db.commit()

        from security_layer.permission_engine import check_document_access
        allowed = await check_document_access(admin.id, org.id, doc.id, db)
        assert allowed is True


class TestCrossOrgIsolation:

    @pytest.mark.asyncio
    async def test_cross_company_denied(self, db):
        """User from Company A must not access Company B organization."""
        org_a, admin_a = await _create_org_with_admin(db, "CompanyA", "business")
        org_b, admin_b = await _create_org_with_admin(db, "CompanyB", "business")

        from security_layer.membership_service import validate_membership
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await validate_membership(admin_a.id, org_b.id, db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_edu_biz_cross_portal_denied(self, db):
        """User from education org must not access business org."""
        edu_org, edu_admin = await _create_org_with_admin(db, "UniA", "education")
        biz_org, biz_admin = await _create_org_with_admin(db, "CompC", "business")

        from security_layer.membership_service import validate_membership
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await validate_membership(edu_admin.id, biz_org.id, db)
        assert exc_info.value.status_code == 403


class TestWorkspaceIsolation:

    @pytest.mark.asyncio
    async def test_workspace_not_in_org_denied(self, db):
        """Workspace not linked to an org must be rejected by resolve_workspace."""
        org, admin = await _create_org_with_admin(db, "WSOrg", "business")
        from security_layer.workspace_service import resolve_workspace
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await resolve_workspace(workspace_id=9999, org_id=org.id, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_workspace_linked_to_org_resolves(self, db):
        """Workspace linked to org resolves successfully."""
        from core.database import Workspace
        org, admin = await _create_org_with_admin(db, "WSOrg2", "business")
        ws = Workspace(name="myws", workspace_type="business", owner_id=admin.id)
        db.add(ws)
        await db.flush()
        from security_layer.workspace_service import link_workspace_to_org, resolve_workspace
        await link_workspace_to_org(ws.id, org.id, db)
        resolved = await resolve_workspace(ws.id, org.id, db)
        assert resolved.id == ws.id


class TestRoleTemplates:

    @pytest.mark.asyncio
    async def test_seed_creates_14_templates(self, db):
        """seed_role_templates must create exactly 14 templates (7 edu + 7 biz)."""
        from security_layer.role_service import seed_role_templates
        from core.database import RoleTemplate
        from sqlalchemy import select, func
        await seed_role_templates(db)
        result = await db.execute(select(func.count()).select_from(RoleTemplate))
        count = result.scalar()
        assert count == 14

    @pytest.mark.asyncio
    async def test_seed_is_idempotent(self, db):
        """Calling seed twice must not duplicate templates."""
        from security_layer.role_service import seed_role_templates
        from core.database import RoleTemplate
        from sqlalchemy import select, func
        await seed_role_templates(db)
        await seed_role_templates(db)
        result = await db.execute(select(func.count()).select_from(RoleTemplate))
        count = result.scalar()
        assert count == 14

    @pytest.mark.asyncio
    async def test_student_has_limited_permissions(self, db):
        """Student role must not have document.approve or audit.read."""
        from security_layer.role_service import seed_role_templates, EDUCATION_ROLES
        await seed_role_templates(db)
        student_role = next(r for r in EDUCATION_ROLES if r["role_name"] == "student")
        assert "document.approve" not in student_role["permissions"]
        assert "audit.read" not in student_role["permissions"]
        assert "document.read" in student_role["permissions"]


class TestAuditLogging:

    @pytest.mark.asyncio
    async def test_audit_event_recorded(self, db):
        """log_event must create an audit record."""
        from security_layer.role_service import seed_role_templates
        await seed_role_templates(db)
        org, admin = await _create_org_with_admin(db, "AuditOrg", "business")
        from security_layer.audit_service import log_event, get_audit_logs
        await log_event(org.id, "test.action", db, admin.id, "workspace", "42")
        logs = await get_audit_logs(org.id, db)
        assert len(logs) >= 1
        assert logs[0].action == "test.action"


class TestExistingRAGRegression:
    """Verify the existing calculation engine and validator still work unchanged."""

    def test_calculation_engine_importable(self):
        """Existing calculation engine must import without errors."""
        from services.analytics.calculation_engine import BusinessCalculationEngine
        assert BusinessCalculationEngine is not None

    def test_analytics_validator_importable(self):
        """Existing analytics validator must import without errors."""
        from services.analytics.analytics_validator import AnalyticsResponseValidator
        assert AnalyticsResponseValidator is not None

    def test_okf_engine_importable(self):
        """Existing OKF engine must import without errors."""
        from services.harness.okf_engine import OKFEngine
        assert OKFEngine is not None
