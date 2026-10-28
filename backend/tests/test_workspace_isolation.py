import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from sqlalchemy import select

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.chat import query
from models.schemas import ChatRequest
from core.database import User, Workspace, Document


@pytest.mark.asyncio
async def test_workspace_isolation_no_admin_bleed():
    """Verify that user querying their workspace does not include workspace_ids from user 1 (admin)."""
    # Create regular user (id=2)
    regular_user = User(id=2, username="regular_user", role="user")

    # Regular user's workspace
    user_workspace = Workspace(id=20, name="User WS", owner_id=2, workspace_type="business")

    # Mock DB session
    mock_db = MagicMock()

    # Mock execute return values
    async def mock_execute(stmt):
        mock_result = MagicMock()
        # When querying for workspace ownership:
        stmt_str = str(stmt)
        if "workspaces.id = :id_1" in stmt_str or "workspaces.owner_id = :owner_id_1" in stmt_str:
            mock_result.scalars.return_value.first.return_value = user_workspace
            mock_result.scalars.return_value.all.return_value = [user_workspace]
        else:
            mock_result.scalars.return_value.first.return_value = None
            mock_result.scalars.return_value.all.return_value = []
        return mock_result

    mock_db.execute = AsyncMock(side_effect=mock_execute)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    payload = ChatRequest(workspace_id=20, question="What are our private metrics?")

    passed_workspace_ids = None

    async def fake_rag_stream(question, workspace_id, workspace_type="business", model=None, **kwargs):
        nonlocal passed_workspace_ids
        passed_workspace_ids = workspace_id
        yield '{"type": "trace", "step": "understanding", "message": "OK"}\n'
        yield "Response"

    with patch("services.rag_engine.rag_stream", side_effect=fake_rag_stream):
        response = await query(payload=payload, current_user=regular_user, db=mock_db)

        # Trigger generator
        async for _ in response.body_iterator:
            pass

        assert passed_workspace_ids == [20], (
            f"Expected workspace_ids=[20], but got {passed_workspace_ids}! Admin workspaces were leaked!"
        )


@pytest.mark.asyncio
async def test_unauthorized_workspace_access_blocked():
    """Verify that a user querying another user's workspace is rejected with 404."""
    user_2 = User(id=2, username="user2", role="user")
    mock_db = MagicMock()

    # Return None for workspace not belonging to user_2
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    payload = ChatRequest(workspace_id=999, question="Secret info")

    with pytest.raises(HTTPException) as exc_info:
        await query(payload=payload, current_user=user_2, db=mock_db)

    assert exc_info.value.status_code == 404
