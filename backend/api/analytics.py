"""
Analytics API routes.
POST /analytics/query          - NL query against Excel/CSV document
GET  /analytics/dashboard      - workspace stats + KPI overview
GET  /analytics/charts/{name}  - serve a saved chart JSON
"""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select

from core.config import settings
from core.database import AuditLog, ChatMessage, ChartHistory, Document, Workspace
from core.deps import CurrentUser, DBSession
from models.schemas import AnalyticsQueryRequest, AnalyticsResponse, DashboardStats, ChartHistoryItem
from services import analytics_engine, chart_generator
from services.harness import default_privacy_guard

router = APIRouter(prefix="/analytics", tags=["Analytics"])
logger = logging.getLogger(__name__)


@router.post("/query", response_model=AnalyticsResponse)
async def analytics_query(payload: AnalyticsQueryRequest, current_user: CurrentUser, db: DBSession):
    """Run a natural-language analytics query against an uploaded data file."""
    # Validate workspace
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == payload.workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Get document
    doc_result = await db.execute(
        select(Document).where(
            Document.id == payload.document_id,
            Document.workspace_id == payload.workspace_id,
        )
    )
    doc = doc_result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.file_type not in ("xlsx", "xls", "csv"):
        raise HTTPException(status_code=400, detail="Analytics only supported for Excel/CSV files")
    if doc.status != "ready":
        raise HTTPException(status_code=400, detail="Document is still processing")

    # Validate privacy guard
    if default_privacy_guard.is_instruction_disclosure_attempt(payload.query):
        return AnalyticsResponse(
            query=payload.query,
            answer=default_privacy_guard.get_secure_refusal_message(),
            chart=None,
            raw_data=None,
        )

    file_path = settings.UPLOAD_DIR / str(payload.workspace_id) / doc.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    result = await analytics_engine.analyze(
        file_path=file_path,
        file_type=doc.file_type,
        query=payload.query,
        chart_type_hint=payload.chart_type,
    )

    # Wrap chart in AnalyticsResponse format and save chart history when available
    from models.schemas import ChartData
    chart = None
    chart_url = None
    if result.get("chart"):
        c = result["chart"]
        chart_url = chart_generator.save_chart(c["plotly_json"], payload.workspace_id)
        chart = ChartData(
            chart_type=c["chart_type"],
            title=c["title"],
            plotly_json=c["plotly_json"],
            insight=result["answer"][:200],
            chart_url=chart_url,
        )

        chart_file = chart_url.split("/")[-1]
        chart_history = ChartHistory(
            workspace_id=payload.workspace_id,
            user_id=current_user.id,
            document_id=doc.id,
            query=payload.query,
            chart_type=c["chart_type"],
            chart_title=c.get("title"),
            chart_file=chart_file,
            answer_snippet=result["answer"][:200],
        )
        db.add(chart_history)

    sanitized_ans = default_privacy_guard.sanitize_output(result["answer"])

    # Persist both user query and assistant response into workspace ChatMessage history
    user_msg = ChatMessage(
        workspace_id=payload.workspace_id,
        user_id=current_user.id,
        role="user",
        content=payload.query,
        chat_type="analytics",
    )
    db.add(user_msg)

    sources_payload = {
        "citations": [{
            "document_name": doc.original_filename,
            "score": 1.0,
            "chunk_text": f"Tabular business analytics query on {doc.original_filename}",
        }],
        "chart": chart.model_dump() if chart else None,
        "raw_data": result.get("raw_data"),
    }
    assistant_msg = ChatMessage(
        workspace_id=payload.workspace_id,
        user_id=current_user.id,
        role="assistant",
        content=sanitized_ans,
        sources=sources_payload,
        chat_type="analytics",
    )
    db.add(assistant_msg)
    db.add(AuditLog(
        user_id=current_user.id,
        action="analytics_query",
        resource="analytics",
        details={"workspace_id": payload.workspace_id, "document_id": doc.id, "query": payload.query[:500]},
    ))
    await db.commit()

    return AnalyticsResponse(
        query=payload.query,
        answer=sanitized_ans,
        chart=chart,
        raw_data=result.get("raw_data"),
    )


@router.get("/history", response_model=list[ChartHistoryItem])
async def chart_history(workspace_id: int, current_user: CurrentUser, db: DBSession):
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    history_result = await db.execute(
        select(ChartHistory)
        .where(
            ChartHistory.workspace_id == workspace_id,
            ChartHistory.user_id == current_user.id,
        )
        .order_by(ChartHistory.created_at.desc())
        .limit(50)
    )
    rows = history_result.scalars().all()
    items = []
    for h in rows:
        chart_url = None
        if getattr(h, 'chart_file', None):
            chart_url = f"/api/analytics/charts/{h.chart_file}"
        elif getattr(h, 'chart_url', None):
            chart_url = h.chart_url
        items.append(ChartHistoryItem(
            id=h.id,
            workspace_id=h.workspace_id,
            document_id=getattr(h, 'document_id', None),
            query=h.query,
            chart_type=getattr(h, 'chart_type', None),
            chart_title=getattr(h, 'chart_title', None),
            chart_url=chart_url,
            answer_snippet=getattr(h, 'answer_snippet', None),
            created_at=h.created_at,
        ))
    return items



@router.delete("/history")
async def clear_chart_history(workspace_id: int, current_user: CurrentUser, db: DBSession):
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    await db.execute(
        delete(ChartHistory).where(
            ChartHistory.workspace_id == workspace_id,
            ChartHistory.user_id == current_user.id,
        )
    )
    await db.commit()
    return {"detail": "Chart history cleared."}


@router.get("/dashboard/{workspace_id}", response_model=DashboardStats)
async def dashboard(workspace_id: int, current_user: CurrentUser, db: DBSession):
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id)
    )
    workspace = ws_result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Document count
    doc_count = (await db.execute(
        select(func.count(Document.id)).where(Document.workspace_id == workspace_id)
    )).scalar() or 0

    # Total chunks
    from sqlalchemy import literal_column
    chunk_sum = (await db.execute(
        select(func.sum(Document.chunk_count)).where(Document.workspace_id == workspace_id)
    )).scalar() or 0

    # Chat count
    chat_count = (await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.workspace_id == workspace_id)
    )).scalar() or 0

    # Recent documents
    recent_result = await db.execute(
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
        .limit(5)
    )
    from models.schemas import DocumentResponse
    recent = [DocumentResponse.model_validate(d) for d in recent_result.scalars().all()]

    return DashboardStats(
        total_documents=doc_count,
        total_chunks=chunk_sum,
        total_chats=chat_count,
        workspace_type=workspace.workspace_type,
        recent_documents=recent,
    )


@router.get("/charts/{chart_file}")
async def get_chart(chart_file: str, current_user: CurrentUser):
    """Serve a saved chart JSON file."""
    # Guard against path traversal: e.g. ../../etc/passwd
    path = (settings.CHARTS_DIR / chart_file).resolve()
    if not str(path).startswith(str(settings.CHARTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid chart file path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Chart not found")
    return FileResponse(str(path), media_type="application/json")
