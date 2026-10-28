"""
Enterprise Offline AI RAG Platform — FastAPI Application Entry Point
"""
import asyncio
import logging
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from telegram_bot.bot import start_polling

from core.config import settings
from core.database import init_db


def _start_bot_thread():
    def _run():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_polling())

    thread = threading.Thread(target=_run, daemon=True, name="telegram-bot")
    thread.start()
    logger.info("Telegram bot thread started.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.LOGS_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("=" * 60)
    logger.info("  Enterprise AI RAG Platform starting up…")
    logger.info(f"  Default LLM : {settings.DEFAULT_LLM_MODEL}")
    logger.info(f"  Embeddings  : {settings.EMBEDDING_MODEL}")
    logger.info(f"  Ollama URL  : {settings.OLLAMA_URL}")
    logger.info("=" * 60)

    # Initialize database tables
    await init_db()
    logger.info("Database initialised.")

    # Enable WAL mode for SQLite to allow concurrent reads/writes
    from core.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=30000"))
    logger.info("SQLite WAL mode enabled.")

    if settings.TELEGRAM_BOT_TOKEN:
        _start_bot_thread()
    else:
        logger.info("Telegram bot token not configured; bot will not start.")

    yield  # ← app runs here

    logger.info("Enterprise AI RAG Platform shutting down.")


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Enterprise Offline AI RAG",
    version=settings.APP_VERSION,
    description="100% offline, privacy-first AI document intelligence platform.",
    lifespan=lifespan,
    # Disable interactive API docs in production (DEBUG must be True to expose them)
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|172\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security Middleware ───────────────────────────────────────────────────────
from fastapi import Request
from fastapi.responses import JSONResponse
import uuid
import traceback

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:"
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    corr_id = str(uuid.uuid4())
    logger.error(f"Correlation ID: {corr_id} - Unhandled Exception: {str(exc)}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "correlation_id": corr_id}
    )

# ── Routers ───────────────────────────────────────────────────────────────────
from api.auth import router as auth_router
from api.workspaces import router as workspaces_router
from api.documents import router as documents_router
from api.chat import router as chat_router
from api.analytics import router as analytics_router
from api.system import router as system_router
from api.summarize import router as summarize_router

app.include_router(auth_router,       prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(documents_router,  prefix="/api")
app.include_router(chat_router,       prefix="/api")
app.include_router(analytics_router,  prefix="/api")
app.include_router(system_router,     prefix="/api")
app.include_router(summarize_router,  prefix="/api")

# ── Static file serving (charts + frontend build) ──────────────────────────
app.mount("/charts", StaticFiles(directory=str(settings.CHARTS_DIR)), name="charts")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=30000, reload=True)
