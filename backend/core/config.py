"""
Central configuration for the Enterprise Offline AI RAG Platform.
All settings can be overridden via environment variables or a .env file.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "Enterprise AI RAG"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Security ─────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # ── CORS ─────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] = [
        "https://localhost:30001",
        "http://localhost:30001",
        "https://127.0.0.1:30001",
        "http://127.0.0.1:30001",
        "https://192.168.0.126:30001",
        "http://192.168.0.126:30001",
        "https://192.168.0.126:30000",
        "http://192.168.0.126:30000",
        "https://192.168.0.130:30001",
        "http://192.168.0.130:30001",
        "https://192.168.0.130:30000",
        "http://192.168.0.130:30000",
        "https://192.168.0.127:30001",
        "http://192.168.0.127:30001",
        "https://192.168.0.127:30000",
        "http://192.168.0.127:30000",
        "https://172.27.0.1:30001",
        "http://172.27.0.1:30001",
        "https://192.168.1.3:30001",
        "http://192.168.1.3:30001",
        os.environ.get("FRONTEND_URL", "https://localhost:30001"),
    ]

    # ── Paths ─────────────────────────────────────────────────────────────────
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    VECTOR_DB_DIR: Path = BASE_DIR / "vector_db"
    CHARTS_DIR: Path = BASE_DIR / "charts"
    LOGS_DIR: Path = BASE_DIR / "logs"
    DATABASE_DIR: Path = BASE_DIR / "database"
    MODELS_DIR: Path = BASE_DIR / "models"
    REPORTS_DIR: Path = BASE_DIR / "reports"

    # ── Database ─────────────────────────────────────────────────────────────
    @property
    def DATABASE_URL(self) -> str:
        return f"sqlite+aiosqlite:///{self.DATABASE_DIR}/rag.db"

    # ── Ollama ───────────────────────────────────────────────────────────────
    OLLAMA_URL: str = "http://localhost:11434"
    DEFAULT_LLM_MODEL: str = "gemma4:12b"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048
    LLM_NUM_CTX: int = 4096

    # ── Embeddings ───────────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_NORMALIZE: bool = True
    EMBEDDING_BATCH_SIZE: int = 32

    # ── RAG ──────────────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    TOP_K_RETRIEVAL: int = 5
    MAX_CONTEXT_LENGTH: int = 4000

    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WORKSPACE_ID: int = 2
    TELEGRAM_WEBHOOK_URL: str = ""
    WEBHOOK_SECRET: str = ""

    # ── Offline Mode ─────────────────────────────────────────────────────────
    OFFLINE_MODE: bool = True  # Prevents accidental HuggingFace network calls

    class Config:
        env_file = (str(BASE_DIR / ".env"), ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars (e.g. ADMIN_PASSWORD used by create_admin.py)


settings = Settings()

# ── Create all required directories ──────────────────────────────────────────
_dirs = [
    settings.UPLOAD_DIR,
    settings.VECTOR_DB_DIR,
    settings.CHARTS_DIR,
    settings.LOGS_DIR,
    settings.DATABASE_DIR,
    settings.MODELS_DIR,
    settings.REPORTS_DIR,
]
for _d in _dirs:
    _d.mkdir(parents=True, exist_ok=True)

# ── Enforce offline mode for HuggingFace ─────────────────────────────────────
if settings.OFFLINE_MODE and (settings.MODELS_DIR / "bge-m3").exists():
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
