"""Database models and async session management."""
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, JSON,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
#  Models
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=True)
    full_name = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user")          # admin | user
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    workspaces = relationship(
        "Workspace", back_populates="owner", cascade="all, delete-orphan"
    )
    chat_messages = relationship("ChatMessage", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    email = Column(String(150), nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    workspace = relationship("Workspace")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    workspace_type = Column(String(20), default="business")  # business | student
    description = Column(Text, nullable=True)
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="workspaces")
    documents = relationship(
        "Document", back_populates="workspace", cascade="all, delete-orphan"
    )
    chat_messages = relationship("ChatMessage", back_populates="workspace")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)          # stored filename (slugified)
    original_filename = Column(String(255), nullable=False)  # original upload name
    file_type = Column(String(20), nullable=False)           # pdf|docx|xlsx|csv|pptx|txt
    file_size = Column(Integer, default=0)
    file_hash = Column(String(255), nullable=True)
    indexing_stage = Column(String(50), default="Pending")
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    status = Column(String(20), default="processing")  # processing | ready | failed
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    doc_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="documents")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(10), nullable=False)   # user | assistant
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)       # list of source citation dicts
    created_at = Column(DateTime, default=datetime.utcnow)
    chat_type = Column(String(20), default="workspace")  # workspace | analytics

    workspace = relationship("Workspace", back_populates="chat_messages")
    user = relationship("User", back_populates="chat_messages")

    @property
    def chart(self):
        if isinstance(self.sources, dict):
            return self.sources.get("chart")
        return None

    @property
    def raw_data(self):
        if isinstance(self.sources, dict):
            return self.sources.get("raw_data")
        return None


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


class ChartHistory(Base):
    __tablename__ = "chart_history"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    document_id = Column(
        Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    query = Column(Text, nullable=False)
    chart_type = Column(String(50), nullable=True)
    chart_title = Column(String(255), nullable=True)
    chart_file = Column(String(255), nullable=False)
    answer_snippet = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace")
    user = relationship("User")
    document = relationship("Document")


# ─────────────────────────────────────────────────────────────────────────────
#  Security & Organization Layer Models
# ─────────────────────────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    org_type = Column(String(20), nullable=False)   # education | business
    slug = Column(String(100), unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    settings_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    departments = relationship("Department", back_populates="organization", cascade="all, delete-orphan")
    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    org_workspaces = relationship("OrgWorkspace", back_populates="organization", cascade="all, delete-orphan")
    org_audit_logs = relationship("OrgAuditLog", back_populates="organization", cascade="all, delete-orphan")


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False)
    dept_type = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="departments")
    children = relationship("Department", backref="parent", remote_side=[id])
    members = relationship("OrganizationMember", back_populates="department")


class RoleTemplate(Base):
    __tablename__ = "role_templates"

    id = Column(Integer, primary_key=True, index=True)
    portal_type = Column(String(20), nullable=False)   # education | business
    role_name = Column(String(50), nullable=False)
    display_name = Column(String(100), nullable=False)
    default_permissions = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrganizationRole(Base):
    __tablename__ = "organization_roles"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(Integer, ForeignKey("role_templates.id", ondelete="SET NULL"), nullable=True)
    custom_permissions = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization")
    template = relationship("RoleTemplate")
    members = relationship("OrganizationMember", back_populates="org_role")


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    org_role_id = Column(Integer, ForeignKey("organization_roles.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    organization = relationship("Organization", back_populates="members")
    department = relationship("Department", back_populates="members")
    org_role = relationship("OrganizationRole", back_populates="members")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    permission_key = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    category = Column(String(50), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id = Column(Integer, ForeignKey("organization_roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)

    role = relationship("OrganizationRole")
    permission = relationship("Permission")


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("organization_roles.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    assigned_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization")
    role = relationship("OrganizationRole")


class OrgWorkspace(Base):
    __tablename__ = "org_workspaces"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    is_public_in_org = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="org_workspaces")
    workspace = relationship("Workspace")


class DocumentACL(Base):
    __tablename__ = "document_acl"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    classification = Column(String(30), default="organization")
    # public | organization | department | restricted | highly_confidential
    allowed_roles = Column(JSON, nullable=True)
    allowed_user_ids = Column(JSON, nullable=True)
    approval_status = Column(String(20), default="draft")
    # draft | review | approved | rejected | revoked
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document")
    organization = relationship("Organization")
    approver = relationship("User", foreign_keys=[approved_by])


class RAGIndexRegistry(Base):
    __tablename__ = "rag_index_registry"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    index_path = Column(String(500), nullable=False)
    index_version = Column(Integer, default=1)
    doc_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    organization = relationship("Organization")
    workspace = relationship("Workspace")


class OrgAuditLog(Base):
    __tablename__ = "org_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    organization = relationship("Organization", back_populates="org_audit_logs")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    status = Column(String(20), default="pending")   # pending | running | done | failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    document = relationship("Document")
    organization = relationship("Organization")


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables if they don't already exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async SQLAlchemy session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
