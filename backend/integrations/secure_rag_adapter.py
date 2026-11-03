"""
Secure RAG adapter — enforces org membership, permissions, and document ACL
BEFORE calling the existing RAG engine. The existing RAG internals are NOT modified.
"""
import logging
from typing import Any, Callable, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from security_layer.membership_service import validate_membership
from security_layer.permission_engine import require_permission, get_authorized_document_ids
from security_layer.workspace_service import resolve_workspace
from security_layer.audit_service import log_event

logger = logging.getLogger(__name__)


async def secure_ask_rag(
    user_id: int,
    organization_id: int,
    workspace_id: int,
    question: str,
    db: AsyncSession,
    existing_rag_fn: Callable,
    extra_kwargs: Optional[Dict[str, Any]] = None,
):
    """
    Secure wrapper around the existing RAG entry point.

    Workflow:
      1. Validate membership
      2. Require workspace.read permission
      3. Validate workspace belongs to org
      4. Get authorized document IDs (ACL-filtered)
      5. Call existing RAG function with constrained doc scope
      6. Audit the event
    """
    # 1. Membership
    await validate_membership(user_id, organization_id, db)

    # 2. Permission
    await require_permission(user_id, organization_id, "workspace.read", db)

    # 3. Workspace belongs to org
    await resolve_workspace(workspace_id, organization_id, db)

    # 4. Authorized documents
    authorized_doc_ids = await get_authorized_document_ids(
        user_id, organization_id, workspace_id, db
    )
    logger.info(
        f"secure_ask_rag: user={user_id} org={organization_id} "
        f"workspace={workspace_id} authorized_docs={authorized_doc_ids}"
    )

    # 5. Call existing RAG (pass doc filter via extra_kwargs)
    kwargs = extra_kwargs or {}
    kwargs["doc_filter_ids"] = authorized_doc_ids
    result = await existing_rag_fn(question=question, workspace_id=workspace_id, **kwargs)

    # 6. Audit
    await log_event(
        org_id=organization_id,
        action="rag.query",
        db=db,
        user_id=user_id,
        resource_type="workspace",
        resource_id=str(workspace_id),
        details={"question_preview": question[:100]},
    )

    return result


async def secure_upload_document(
    user_id: int,
    organization_id: int,
    workspace_id: int,
    document_id: int,
    classification: str,
    db: AsyncSession,
):
    """
    Post-upload ACL registration. Call this AFTER the existing document ingestion
    pipeline has created the Document record.
    """
    from security_layer.membership_service import validate_membership
    from security_layer.permission_engine import require_permission
    from security_layer.workspace_service import resolve_workspace
    from security_layer.document_acl_service import create_acl, approve_document
    from security_layer.audit_service import log_event
    from security_layer.role_service import get_user_permissions

    await validate_membership(user_id, organization_id, db)
    await require_permission(user_id, organization_id, "document.upload", db)
    await resolve_workspace(workspace_id, organization_id, db)

    # Determine auto-approve: roles with document.approve permission auto-approve
    perms = await get_user_permissions(user_id, organization_id, db)
    auto_approve = "document.approve" in perms

    acl = await create_acl(
        document_id=document_id,
        org_id=organization_id,
        db=db,
        classification=classification,
        allowed_roles=[],
        allowed_user_ids=[],
    )

    if auto_approve:
        acl = await approve_document(document_id, organization_id, user_id, db)

    await log_event(
        org_id=organization_id,
        action="document.upload",
        db=db,
        user_id=user_id,
        resource_type="document",
        resource_id=str(document_id),
        details={"classification": classification, "auto_approved": auto_approve},
    )
    return acl
