"""
Pydantic schemas for all API request/response models.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
        return value


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    chat_type: Optional[str] = "workspace"

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
#  Workspace
# ─────────────────────────────────────────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    workspace_type: str = Field("business", pattern="^(business|student)$")
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    workspace_type: str
    description: Optional[str]
    owner_id: int
    created_at: datetime
    document_count: int = 0

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
#  Documents
# ─────────────────────────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: int
    original_filename: str
    file_type: str
    file_size: int
    workspace_id: int
    status: str
    chunk_count: int
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
#  Chat
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    workspace_id: int
    model: Optional[str] = None           # override default model
    stream: bool = True


class SourceCitation(BaseModel):
    document_name: str
    chunk_text: str
    score: float
    page: Optional[int] = None


class ChatResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    answer: str
    sources: list[SourceCitation] = []
    model_used: str
    workspace_id: int


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[list[dict]] = None
    chart: Optional[dict] = None
    raw_data: Optional[list] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator("sources", mode="before")
    @classmethod
    def extract_sources(cls, v):
        if isinstance(v, dict):
            return v.get("citations")
        return v


class SummarizeRequest(BaseModel):
    """Request body for POST /api/summarize."""
    input_type: Optional[str] = "auto"          # auto|youtube|url|document|text
    content: Optional[str] = None               # pasted text
    url: Optional[str] = None                   # YouTube or web article URL
    document_id: Optional[int] = None           # existing document in the workspace
    workspace_id: Optional[int] = None          # workspace context (for doc ownership check)
    summary_type: Optional[str] = "quick"       # quick|detailed|simple|study|executive|keypoints

# ─────────────────────────────────────────────────────────────────────────────
#  Analytics
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    document_id: int
    workspace_id: int
    chart_type: Optional[str] = None     # auto-detect if None


class ChartData(BaseModel):
    chart_type: str                       # bar | line | pie | scatter | table
    title: str
    plotly_json: dict                     # Plotly figure JSON
    insight: Optional[str] = None        # AI-generated insight
    chart_url: Optional[str] = None


class AnalyticsResponse(BaseModel):
    query: str
    answer: str
    chart: Optional[ChartData] = None
    raw_data: Optional[list[dict]] = None


class ChartHistoryItem(BaseModel):
    id: int
    workspace_id: int
    document_id: Optional[int] = None
    query: str
    chart_type: Optional[str] = None
    chart_title: Optional[str] = None
    chart_url: Optional[str] = None
    answer_snippet: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        # chart_file in DB → chart_url in schema
        if hasattr(obj, 'chart_file') and not getattr(obj, 'chart_url', None):
            chart_file = getattr(obj, 'chart_file', None)
            if chart_file:
                obj.__dict__['chart_url'] = f"/api/analytics/charts/{chart_file}"
        return super().model_validate(obj, *args, **kwargs)


class AdminAuditLogItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None
    action: str
    resource: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminConversationItem(BaseModel):
    id: int
    workspace_id: int
    workspace_name: str
    user_id: int
    username: str
    user_role: Optional[str] = None
    role: str
    content: str
    sources: Optional[list[dict]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminHistoryResponse(BaseModel):
    login_history: list[AdminAuditLogItem]
    conversation_history: list[AdminConversationItem]


class DashboardStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_chats: int
    workspace_type: str
    recent_documents: list[DocumentResponse]


# ─────────────────────────────────────────────────────────────────────────────
#  System
# ─────────────────────────────────────────────────────────────────────────────

class OllamaModelInfo(BaseModel):
    name: str
    size: Optional[int] = None
    modified_at: Optional[str] = None


class SystemStatus(BaseModel):
    ollama_online: bool
    available_models: list[str]
    embedding_model: str
    default_llm: str
    total_documents: int
    total_workspaces: int
    version: str
