import re
"""Telegram bot handlers for command and message processing."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger
from telegram import Update, Message
from telegram.constants import ParseMode, ChatAction
from telegram.error import RetryAfter, BadRequest, TelegramError
from telegram.ext import ContextTypes

from core.config import settings
from core.database import (
    AsyncSessionLocal,
    ChatMessage,
    Document,
    TelegramUser,
    User,
    Workspace,
)
from services import rag_engine
from services.document_processor import process_document
from services.vector_store import add_documents
from telegram_bot.keyboards import (
    main_menu_keyboard,
    subject_keyboard,
    category_keyboard,
    back_keyboard,
    scheme_keyboard,
    branch_keyboard,
    semester_keyboard,
    subject_dashboard_keyboard,
    pdf_list_keyboard,
    answer_type_keyboard,
)
from telegram_bot.states import get_session, set_session, ConversationState

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".ppt", ".txt", ".md",
    ".json", ".html", ".htm", ".py", ".java", ".c", ".cpp", ".rtf", ".png", ".jpg", ".jpeg"
}

from sqlalchemy import select, or_
import uuid


async def _get_workspaces_for_user(user_id: int) -> list[Workspace]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace).where(Workspace.owner_id == user_id).order_by(Workspace.created_at.desc())
        )
        return result.scalars().all()


async def _find_user_by_email(email: str) -> Optional[User]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalars().first()


async def _get_or_create_telegram_user(telegram_id: int) -> TelegramUser:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
        tg_user = result.scalars().first()
        if tg_user is None:
            tg_user = TelegramUser(telegram_id=telegram_id)
            db.add(tg_user)
            await db.commit()
            await db.refresh(tg_user)
        return tg_user


async def _register_user(update: Update) -> Optional[TelegramUser]:
    tg_id = update.effective_user.id
    tg_user = await _get_or_create_telegram_user(tg_id)
    session = get_session(tg_id)
    if tg_user.user_id:
        session["user_id"] = tg_user.user_id
    return tg_user


async def _link_telegram_user_to_email(telegram_id: int, email: str) -> TelegramUser:
    email = email.strip().lower()
    user = await _find_user_by_email(email)

    async with AsyncSessionLocal() as db:
        if user is None:
            import uuid
            from core.security import hash_password
            base_username = email.split("@")[0][:25]
            unique_username = f"{base_username}_{uuid.uuid4().hex[:6]}"
            user = User(
                username=unique_username,
                email=email,
                full_name=base_username.capitalize(),
                hashed_password=hash_password(uuid.uuid4().hex),
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            # Create default workspace
            workspace = Workspace(
                name="General Workspace",
                owner_id=user.id,
                workspace_type="student",
            )
            db.add(workspace)
            await db.commit()
            await db.refresh(workspace)
            workspace_id = workspace.id
        else:
            ws_res = await db.execute(
                select(Workspace).where(Workspace.owner_id == user.id).order_by(Workspace.created_at.asc())
            )
            workspace = ws_res.scalars().first()
            if not workspace:
                base_username = email.split("@")[0][:25]
                workspace = Workspace(
                    name="General Workspace",
                    owner_id=user.id,
                    workspace_type="student",
                )
                db.add(workspace)
                await db.commit()
                await db.refresh(workspace)
            workspace_id = workspace.id

        result = await db.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
        tg_user = result.scalars().first()
        if tg_user is None:
            tg_user = TelegramUser(telegram_id=telegram_id)
            db.add(tg_user)

        tg_user.email = email
        tg_user.user_id = user.id
        tg_user.workspace_id = workspace_id

        await db.commit()
        await db.refresh(tg_user)

        session = get_session(telegram_id)
        session["user_id"] = user.id
        session["workspace_id"] = workspace_id
        return tg_user


async def _get_linked_workspace(telegram_id: int) -> Optional[Workspace]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
        tg_user = result.scalars().first()
        if tg_user is None or tg_user.workspace_id is None:
            return None

        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == tg_user.workspace_id, Workspace.owner_id == tg_user.user_id)
        )
        return ws_result.scalars().first()


async def _get_default_workspace() -> Optional[Workspace]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace).where(Workspace.id == settings.TELEGRAM_WORKSPACE_ID)
        )
        return result.scalars().first()


async def _select_workspace_for_telegram(telegram_id: int, workspace_id: int) -> Optional[Workspace]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))
        tg_user = result.scalars().first()
        if tg_user is None or tg_user.user_id is None:
            return None
        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == tg_user.user_id)
        )
        workspace = ws_result.scalars().first()
        if workspace is None:
            return None
        tg_user.workspace_id = workspace.id
        await db.commit()
        await db.refresh(tg_user)
        return workspace


async def _save_chat_history(
    user_id: int,
    workspace_id: int,
    question: str,
    answer: str,
    sources: list[dict],
):
    async with AsyncSessionLocal() as db:
        user_msg = ChatMessage(
            workspace_id=workspace_id,
            user_id=user_id,
            role="user",
            content=question,
            sources=[],
        )
        db.add(user_msg)
        await db.commit()
        assistant_msg = ChatMessage(
            workspace_id=workspace_id,
            user_id=user_id,
            role="assistant",
            content=answer,
            sources=sources,
        )
        db.add(assistant_msg)
        await db.commit()


# Helpers

def _split_long_message(text: str, limit: int = 4000) -> list[str]:
    parts = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    parts.append(text)
    return parts


def _truncate_to_sentences(text: str, max_sentences: int = 2) -> str:
    """Cut the text to at most `max_sentences` sentences.
    This is used for short answers to prevent the small LLM from drifting into related topics.
    """
    import re
    # Split on sentence-ending punctuation followed by a space or end-of-string
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter out empty entries
    sentences = [s for s in sentences if s.strip()]
    # Take only the first max_sentences
    truncated = " ".join(sentences[:max_sentences])
    # Ensure it ends with punctuation
    if truncated and truncated[-1] not in ".!?":
        truncated += "."
    return truncated


def _deduplicate_paragraphs(text: str) -> str:
    """Remove repeated paragraphs and sentences from LLM output.
    Small models often loop by repeating the same paragraph 2-3 times.
    """
    import re

    # Step 1: Deduplicate by paragraph (split on blank lines)
    paragraphs = re.split(r'\n{2,}', text.strip())
    seen_paras = []
    seen_para_set = set()
    for para in paragraphs:
        normalized = re.sub(r'\s+', ' ', para.strip().lower())
        if normalized and normalized not in seen_para_set:
            seen_para_set.add(normalized)
            seen_paras.append(para.strip())

    deduped = "\n\n".join(seen_paras)

    # Step 2: Deduplicate sentences within paragraphs
    sentences = re.split(r'(?<=[.!?])\s+', deduped)
    seen_sents = []
    seen_sent_set = set()
    for sent in sentences:
        normalized = re.sub(r'\s+', ' ', sent.strip().lower())
        if normalized and normalized not in seen_sent_set:
            seen_sent_set.add(normalized)
            seen_sents.append(sent.strip())

    return " ".join(seen_sents)


def _strip_urls(text: str) -> str:
    """Remove any URLs hallucinated by the LLM from the answer."""
    import re
    # Remove http/https URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove bare domain-like patterns (e.g. vtucircle.com, github.com/...)
    text = re.sub(r'\b[\w.-]+\.(com|org|net|edu|io|in|gov|co)\S*', '', text)
    # Clean up leftover whitespace/punctuation
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _clean_leaked_prompts(text: str) -> str:
    """TinyLlama/qwen often leaks parts of its prompt. Strip them out."""
    import re
    # Remove things like "Question: xxx Answer:" that it echoes back
    text = re.sub(r'(?i)Question:.*?Answer:\s*', '', text, flags=re.DOTALL)
    text = re.sub(r'(?i)IMPORTANT INSTRUCTION:.*', '', text)
    text = re.sub(r'(?i)Use the text( below)?( as a direct answer)?.*?question.*?:', '', text, flags=re.DOTALL)
    text = re.sub(r'(?i)^(Question|Answer|Direct Answer|Document content|Context):\s*', '', text)
    text = re.sub(r'(?i)Based on the context provided.*?:', '', text)
    text = re.sub(r'(?i)^Write a structured summary.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'(?i)^Answer by listing.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'(?i)^Answer directly.*$', '', text, flags=re.MULTILINE)
    text = text.replace("Answer:", "").replace("Question:", "")
    return text.strip()



async def _send_long(message: Message, text: str, **kwargs):
    # Strip hallucinated URLs and leaked prompts before sending
    text = _strip_urls(text)
    text = _clean_leaked_prompts(text)
    
    # Always disable link previews so no URL cards appear
    kwargs.setdefault("disable_web_page_preview", True)
    parts = _split_long_message(text)
    for i, part in enumerate(parts):
        for attempt in range(2):
            try:
                await message.reply_text(part, **kwargs)
                break
            except RetryAfter as e:
                logger.warning(f"RetryAfter in _send_long: waiting {e.retry_after}s")
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                plain_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                try:
                    await message.reply_text(part, **plain_kwargs)
                    break
                except RetryAfter as e:
                    logger.warning(f"RetryAfter in _send_long fallback: waiting {e.retry_after}s")
                    await asyncio.sleep(e.retry_after + 1)
                except Exception:
                    break
        if i < len(parts) - 1:
            await asyncio.sleep(0.5)


def _match_document_in_query(question: str, documents: list[Document]) -> Optional[Document]:
    """Find if a document in documents is mentioned in question."""
    if not question or not documents:
        return None

    def _clean_str(s: str) -> str:
        return re.sub(r'[^a-zA-Z0-9\s]', ' ', s).lower()

    STOPWORDS = {
        'module', 'notes', 'paper', 'assignment', 'syllabus', 'document',
        'file', 'unit', 'sample', 'samples', 'chapter', 'part', 'test',
        'docx', 'pdf', 'xlsx', 'csv', 'pptx', 'txt', 'doc', 'text'
    }

    q_clean = _clean_str(question)
    q_words = set(q_clean.split())
    q_squashed = q_clean.replace(" ", "")

    # 1. Exact full stem match (e.g. "AD011_IEEE", "BCS502-module-1")
    for doc in documents:
        for name in [doc.original_filename, doc.filename]:
            if not name:
                continue
            stem = re.sub(r'\.(pdf|docx|xlsx|csv|pptx|txt|doc|md)$', '', name, flags=re.IGNORECASE)
            stem_clean = _clean_str(stem).strip()
            stem_squashed = stem_clean.replace(" ", "")
            if stem_clean and stem_clean in q_clean:
                return doc
            if stem_squashed and len(stem_squashed) >= 4 and stem_squashed in q_squashed:
                return doc

    # 2. Distinctive token match (e.g. "AD011", "BAD601", "BCS502", "Kunal")
    for doc in documents:
        for name in [doc.original_filename, doc.filename]:
            if not name:
                continue
            stem = re.sub(r'\.(pdf|docx|xlsx|csv|pptx|txt|doc|md)$', '', name, flags=re.IGNORECASE)
            tokens = [t for t in _clean_str(stem).split() if len(t) >= 3 and t not in STOPWORDS]
            for tok in tokens:
                if tok in q_words or re.search(r'\b' + re.escape(tok) + r'\b', q_clean):
                    return doc

    return None



async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _register_user(update)
    if not user:
        await update.message.reply_text("❌ Your account is restricted.")
        return

    welcome = (
        "🎓 *Welcome to Enterprise AI RAG!*\n\n"
        "Use /ask to query your documents, /upload to send a PDF for indexing, /download to fetch ready PDFs, or /help for more commands."
    )
    await update.message.reply_text(
        welcome,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 *Telegram Bot Help*\n\n"
        "/link your-email@example.com — Link your account by email\n"
        "/upload — Send a PDF file to index it into your selected workspace\n"
        "/download — Download a PDF uploaded by an admin\n"
        "/ask — Ask a question from your documents\n"
        "/summary — Generate a summary\n"
        "/important_questions — Important questions\n"
        "/pyq — Browse previous year questions\n"
        "/quiz — Generate a quiz\n"
        "/timetable — Generate a study timetable\n"
        "/explain — Explain a topic simply\n"
        "/vtu — VTU-style answer\n"
        "/subjects — List available workspaces\n"
    )
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    email = " ".join(context.args).strip() if context.args else ""
    if not email:
        session = get_session(update.effective_user.id)
        session["state"] = ConversationState.WAITING_EMAIL
        await update.message.reply_text(
            "📧 Please reply with your Gmail / email address to link your account:",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    email = email.lower()
    linked = await _link_telegram_user_to_email(update.effective_user.id, email)
    session = get_session(update.effective_user.id)
    workspace = await _get_current_workspace(update.effective_user.id, session)
    ws_name = workspace.name if workspace else "Default"
    await update.message.reply_text(
        f"✅ Telegram account linked to *{email}*!\n"
        f"📁 Workspace: *{ws_name}*\n\n"
        "You can now upload any document (PDF, Word, PPT, Excel, etc.) or ask any questions.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def subjects_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    default_workspace = await _get_default_workspace()
    if not tg_user.user_id and default_workspace is None:
        await update.message.reply_text(
            "🔗 Please link your account first with /link your-email@example.com or upload a document from the website.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if tg_user.user_id:
        workspaces = await _get_workspaces_for_user(tg_user.user_id)
        if workspaces:
            items = [{"id": ws.id, "name": ws.name} for ws in workspaces]
            set_session(update.effective_user.id, state=ConversationState.WAITING_SUBJECT_SELECT, pending_action="select_workspace")
            await update.message.reply_text(
                "🎓 *Select a Workspace*\n\nChoose the workspace to use for questions and uploads:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=subject_keyboard(items),
            )
            return

    if default_workspace:
        set_session(update.effective_user.id, state=ConversationState.IDLE, workspace_id=default_workspace.id)
        await update.message.reply_text(
            f"🎓 Using the default workspace: *{default_workspace.name}*\n\nYou can now ask questions from uploaded documents.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return

    await update.message.reply_text(
        "📁 No workspace is available. Upload a PDF from the website to make documents available for Telegram.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    session = get_session(update.effective_user.id)
    if not tg_user.user_id or not tg_user.email:
        session["state"] = ConversationState.WAITING_EMAIL
        await update.message.reply_text(
            "📧 *Please enter your Gmail / email address to link your workspace:*\n"
            "(Once linked, you can send any document to chunk and index it!)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    workspace = await _get_current_workspace(update.effective_user.id, session)
    ws_name = workspace.name if workspace else "My Workspace"
    await update.message.reply_text(
        f"📤 *Send any document in this chat!*\n\n"
        f"📁 Target workspace: *{ws_name}*\n"
        f"📄 Supported formats: PDF (`.pdf`), Word (`.docx`, `.doc`), PowerPoint (`.pptx`, `.ppt`), Excel/CSV (`.xlsx`, `.xls`, `.csv`), Text (`.txt`, `.md`).\n\n"
        f"I will chunk it, index it into your workspace, and then you can ask any questions from it!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def ask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    query = " ".join(context.args) if context.args else ""
    if query:
        await _do_answer_question(update, context, query, "qa", "detailed")
        return

    session = get_session(update.effective_user.id)
    session["state"] = ConversationState.WAITING_QUESTION
    await update.message.reply_text(
        "🧠 *Ask your question! I am ready to answer from your documents.*",
        parse_mode=ParseMode.MARKDOWN,
    )


async def summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if query:
        await _do_summarize(update, context, query)
        return

    session = get_session(update.effective_user.id)
    session["state"] = ConversationState.WAITING_SUMMARY_INPUT
    await update.message.reply_text(
        "📝 Send me a YouTube link, an article URL, or plain text to summarize.",
        parse_mode=ParseMode.MARKDOWN,
    )

async def _do_summarize(update: Update, context: ContextTypes.DEFAULT_TYPE, content: str):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("⏳ Processing summary request...")

    from services.summarization.source_detector import detect_source_type
    from services.summarization.youtube_extractor import extract_youtube_transcript
    from services.summarization.web_extractor import extract_web_article
    from services.summarization.summarization_engine import summarize_stream

    detected = detect_source_type(content=content, url=None, document_id=None, input_type="auto")
    source_type = detected["source_type"]
    summary_type = "detailed" # default for TG

    extracted_content = ""
    source_label = "Pasted text"
    
    if source_type == "youtube":
        await msg.edit_text("⏳ Extracting YouTube transcript...")
        res = extract_youtube_transcript(detected["video_id"])
        if not res["success"]:
            await msg.edit_text(f"❌ Error: {res['error']}")
            return
        extracted_content = res["transcript"]
        source_label = res["title"]
    elif source_type == "url":
        await msg.edit_text("⏳ Downloading article...")
        res = extract_web_article(detected["url"])
        if not res["success"]:
            await msg.edit_text(f"❌ Error: {res['error']}")
            return
        extracted_content = res["content"]
        source_label = res["title"]
    else:
        extracted_content = content
    
    await msg.edit_text("⏳ Generating summary (this may take a moment)...")

    full_summary = ""
    async for token in summarize_stream(extracted_content, summary_type, source_label, source_type):
        full_summary += token
    
    await _send_long(update.message, full_summary, parse_mode=ParseMode.MARKDOWN)
    await msg.delete()


async def important_questions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    query = " ".join(context.args) if context.args else ""
    if query:
        await _do_answer_question(
            update, context,
            f"Extract and list the top 10 most important exam questions regarding {query} based on the documents. For each question, explain key concepts and provide an outline of the answer.",
            mode="qa", answer_style="detailed"
        )
        return

    session = get_session(update.effective_user.id)
    session["state"] = ConversationState.WAITING_IMP_QUESTIONS
    await update.message.reply_text(
        "⭐ *Important Exam Questions Generator*\n\n"
        "Send the subject, module, or topic name (e.g. *Module 1*, *Data Communication*, *Big Data*), "
        "or reply *all* to generate from all uploaded documents:",
        parse_mode=ParseMode.MARKDOWN,
    )


async def pyq_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    query = " ".join(context.args) if context.args else ""
    if query:
        await _do_answer_question(
            update, context,
            f"List previous year university exam questions (PYQs) and frequent exam questions on {query} from the documents, along with mark allocations and key answer points.",
            mode="qa", answer_style="detailed"
        )
        return

    session = get_session(update.effective_user.id)
    session["state"] = ConversationState.WAITING_PYQ_INPUT
    await update.message.reply_text(
        "📋 *Previous Year Questions (PYQs)*\n\n"
        "Send the subject or module name to extract past university exam questions (e.g. *BCS502*, *Module 1*, *Data Communication*), "
        "or reply *all* to browse from all documents:",
        parse_mode=ParseMode.MARKDOWN,
    )


async def quiz_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    query = " ".join(context.args) if context.args else ""
    if query:
        await _do_answer_question(
            update, context,
            f"Generate a 5-question multiple choice quiz (MCQ) on {query} based on the documents. Include 4 options (A, B, C, D) for each question, and provide the correct answers and explanations at the end.",
            mode="quiz", answer_style="detailed"
        )
        return

    session = get_session(update.effective_user.id)
    session["state"] = ConversationState.WAITING_QUIZ_INPUT
    await update.message.reply_text(
        "🧪 *Quiz Generator*\n\n"
        "Send the topic or subject for the quiz (e.g. *Data Communication*, *Big Data*, *Module 1*), "
        "or reply *all* to quiz from current documents:",
        parse_mode=ParseMode.MARKDOWN,
    )


async def timetable_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    query = " ".join(context.args) if context.args else ""
    if not query:
        query = "Generate a comprehensive 7-day revision study timetable for the topics and modules in the uploaded documents."

    await _do_answer_question(
        update, context,
        f"Create a structured, daily study and revision timetable for: {query}. Include morning and evening study sessions, specific document chapters to cover, and self-test checkpoints.",
        mode="qa", answer_style="detailed"
    )


async def explain_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if query:
        await _process_question(update, context, query, None, "simple")
        return
    await update.message.reply_text("🧒 Send a topic to explain in simple words.")


async def vtu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if query:
        await _process_question(update, context, query, None, "vtu")
        return
    await update.message.reply_text("🎓 Send a VTU-style question to answer.")


async def mydocs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all documents in the user's personal workspace."""
    tg_user = await _register_user(update)
    session = get_session(update.effective_user.id)
    workspace = await _get_current_workspace(update.effective_user.id, session)
    if workspace is None:
        await update.message.reply_text("📁 No workspace selected. Use /subjects first.")
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(Document.workspace_id == workspace.id).order_by(Document.created_at.desc())
        )
        docs = result.scalars().all()

    if not docs:
        await update.message.reply_text("📂 No documents found in your workspace.")
        return

    doc_list = "\n".join(f"• {d.original_filename}" for d in docs)
    await update.message.reply_text(
        f"📂 *Documents in workspace '{workspace.name}':*\n\n{doc_list}\n\n"
        f"To delete a document: `/deletedoc Filename.pdf`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def deletedoc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a document from the user's workspace by filename."""
    tg_user = await _register_user(update)
    session = get_session(update.effective_user.id)
    workspace = await _get_current_workspace(update.effective_user.id, session)
    if workspace is None:
        await update.message.reply_text("📁 No workspace selected. Use /subjects first.")
        return

    filename = " ".join(context.args).strip() if context.args else ""
    if not filename:
        await update.message.reply_text(
            "❓ Usage: `/deletedoc Filename.pdf`\n\nUse /mydocs to see your document list.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(
                Document.workspace_id == workspace.id,
                Document.original_filename == filename,
            )
        )
        doc = result.scalars().first()

        if doc is None:
            # Try partial match
            result2 = await db.execute(
                select(Document).where(
                    Document.workspace_id == workspace.id,
                    Document.original_filename.ilike(f"%{filename}%"),
                )
            )
            doc = result2.scalars().first()

        if doc is None:
            await update.message.reply_text(
                f"❌ Document '{filename}' not found in your workspace.\n\nUse /mydocs to see exact filenames.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        doc_name = doc.original_filename
        doc_id = doc.id
        await db.delete(doc)
        await db.commit()

    # Remove from FAISS index
    try:
        from services import vector_store
        vector_store.delete_document(workspace.id, doc_id)
        index_msg = "✅ Also removed from search index."
    except Exception as e:
        logger.warning(f"Could not remove from FAISS index: {e}")
        index_msg = "⚠️ Removed from database but could not update search index (will be excluded on next restart)."


    await update.message.reply_text(
        f"🗑️ *Deleted:* `{doc_name}`\n{index_msg}\n\nUse /mydocs to see remaining documents.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    tg_id = update.effective_user.id
    session = get_session(tg_id)

    if data == "cancel":
        set_session(tg_id, state=ConversationState.IDLE)
        await query.edit_message_text(
            "❌ Cancelled. Use /subjects to choose a workspace.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data.startswith("ans_type:"):
        answer_style = data.split(":", 1)[1]  # "short" or "detailed"
        question = session.get("pending_question")
        mode = session.get("pending_mode", "qa")

        if not question:
            await query.edit_message_text(
                "❌ No question found. Please type your question again.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        session.pop("pending_question", None)
        session.pop("pending_mode", None)

        label = "📝 Short Definition" if answer_style == "short" else "📖 Detailed Explanation"
        await query.edit_message_text(
            f"{label}\n\n⏳ Searching documents...",
            parse_mode=ParseMode.MARKDOWN,
        )

        await _do_answer_question(update, context, question, mode, answer_style)
        return

    if data.startswith("doc_select:"):
        selection = data.split(":", 1)[1]  # index or "all"
        question = session.get("pending_question")
        mode = session.get("pending_mode", "qa")
        answer_style = session.get("pending_answer_style", "short")
        doc_names = session.get("pending_doc_names", [])

        if not question:
            await query.edit_message_text(
                "❌ Session expired. Please type your question again.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Clean up session
        session.pop("pending_question", None)
        session.pop("pending_mode", None)
        session.pop("pending_answer_style", None)
        session.pop("pending_doc_names", None)

        if selection == "all":
            chosen_label = "All Documents"
        else:
            idx = int(selection)
            chosen_label = doc_names[idx] if idx < len(doc_names) else "Selected Document"

        label = "📝 Short Definition" if answer_style == "short" else "📖 Detailed Explanation"
        await query.edit_message_text(
            f"{label} from *{chosen_label}*\n\n⏳ Searching...",
            parse_mode=ParseMode.MARKDOWN,
        )

        # If a specific doc was selected, narrow the question context with the filename
        if selection != "all" and doc_names:
            idx = int(selection)
            selected_name = doc_names[idx]
            # Pass the selected doc name into the answer function via session
            session["filter_doc_name"] = selected_name

        await _do_answer_question(update, context, question, mode, answer_style)
        # Clean up doc filter
        session.pop("filter_doc_name", None)
        return

    if data.startswith("subject:"):


        workspace_id = int(data.split(":", 1)[1])
        workspace = await _select_workspace_for_telegram(tg_id, workspace_id)
        if workspace is None:
            await query.edit_message_text(
                "❌ Workspace selection failed. Make sure it belongs to your account.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        set_session(tg_id, state=ConversationState.IDLE, workspace_id=workspace.id)
        await query.edit_message_text(
            f"✅ Selected workspace: *{workspace.name}*\n\nYou can now upload a PDF, ask questions, or download ready documents.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=subject_dashboard_keyboard(),
        )
        return

    if data == "action:upload":
        workspace = await _get_current_workspace(tg_id, session)
        if workspace is None:
            await query.edit_message_text(
                "📁 No workspace is available. Please use /subjects to select a workspace first.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        await query.edit_message_text(
            f"📤 Send your PDF file in this chat. I will upload it to workspace *{workspace.name}* and index it for RAG questions.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "action:download":
        # Always list PDFs from the admin so every user can download them
        documents = await _list_admin_documents()
        if not documents:
            await query.edit_message_text(
                "📁 No PDFs are available yet. Please ask the admin to upload documents from the website.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        items = [{"id": d.id, "original_name": d.original_filename} for d in documents]
        await query.edit_message_text(
            f"📄 *{len(items)} PDF(s) available*\n\nChoose one to download:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=pdf_list_keyboard(items),
        )
        return

    if data.startswith("dl_pdf:"):
        doc_id = int(data.split(":", 1)[1])
        # Fetch doc from database directly (users can download any admin-uploaded PDF)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Document)
                .where(
                    Document.id == doc_id,
                    Document.status == "ready",
                )
            )
            document = result.scalars().first()

        if document is None:
            await query.edit_message_text(
                "❌ That PDF could not be found or is not ready yet.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        file_path = settings.UPLOAD_DIR / str(document.workspace_id) / document.filename
        if not file_path.exists():
            await query.edit_message_text(
                "❌ The file is missing from the server. Please ask the admin to re-upload it.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        await query.edit_message_text(
            f"📤 Sending *{document.original_filename}*...",
            parse_mode=ParseMode.MARKDOWN,
        )
        with open(file_path, "rb") as f:
            await update.effective_chat.send_document(
                document=f,
                filename=document.original_filename,
                caption=f"📄 {document.original_filename}",
            )
        return

    await query.edit_message_text("Unknown action.")


async def _process_and_index_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    file_name: str,
    file_size: int,
    file_type: str,
    file_ext: str,
    workspace: Workspace,
):
    await update.effective_message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
    processing_msg = await update.effective_message.reply_text(
        f"⏳ *Downloading and indexing {file_name}...*\n\n"
        f"📁 Workspace: *{workspace.name}*\n"
        "Please wait while text is extracted and searchable chunks are generated...",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        tg_file = await context.bot.get_file(file_id)
        tmp_path = Path(tempfile.mktemp(suffix=file_ext))
        await tg_file.download_to_drive(str(tmp_path))

        workspace_dir = settings.UPLOAD_DIR / str(workspace.id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}_{file_name.replace(' ', '_')}"
        dest_path = workspace_dir / stored_name
        tmp_path.rename(dest_path)

        async with AsyncSessionLocal() as db:
            record = Document(
                filename=stored_name,
                original_filename=file_name,
                file_type=file_type,
                file_size=file_size,
                workspace_id=workspace.id,
                status="processing",
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            doc_id = record.id

        chunks = await asyncio.to_thread(
            process_document,
            file_path=dest_path,
            file_type=file_type,
            doc_id=doc_id,
            filename=file_name,
            workspace_id=workspace.id,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

        if not chunks:
            raise ValueError("No readable text could be extracted from this document.")

        added = await asyncio.to_thread(add_documents, workspace.id, chunks)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc_record = result.scalars().first()
            if doc_record:
                doc_record.status = "ready"
                doc_record.chunk_count = added
                await db.commit()

        await processing_msg.edit_text(
            f"✅ *{file_name}* indexed successfully!\n\n"
            f"📁 Workspace: *{workspace.name}*\n"
            f"📊 Created *{added}* searchable chunks.\n\n"
            f"💡 *You can now ask any question from this document directly in this chat!*",
            parse_mode=ParseMode.MARKDOWN,
        )

    except Exception as exc:
        logger.exception("Document processing failed for %s", file_name)
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Document).where(Document.original_filename == file_name, Document.workspace_id == workspace.id)
                )
                doc_record = result.scalars().first()
                if doc_record:
                    doc_record.status = "failed"
                    doc_record.error_message = str(exc)[:500]
                    await db.commit()
        except Exception:
            pass

        await processing_msg.edit_text(
            f"❌ Failed to process *{file_name}*:\n`{str(exc)[:250]}`",
            parse_mode=ParseMode.MARKDOWN,
        )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photos and scanned images with OCR."""
    if not update.message.photo:
        return

    tg_user = await _register_user(update)
    if not tg_user:
        return

    photo = update.message.photo[-1]
    file_name = f"photo_{photo.file_unique_id[:8]}.jpg"
    file_type = "jpg"
    file_ext = ".jpg"

    session = get_session(update.effective_user.id)

    if not tg_user.user_id or not tg_user.email:
        session["pending_doc"] = {
            "file_id": photo.file_id,
            "file_name": file_name,
            "file_size": photo.file_size or 0,
            "file_type": file_type,
            "file_ext": file_ext,
        }
        session["state"] = ConversationState.WAITING_EMAIL
        await update.message.reply_text(
            f"📸 Received image *{file_name}*!\n\n"
            "📧 *Please enter your Gmail / email address to link your workspace:*\n\n"
            "*(Once you provide your email, text from this image will be automatically extracted, chunked, and indexed into your General Workspace!)*",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    workspace = await _get_current_workspace(update.effective_user.id, session)
    if workspace is None:
        await update.message.reply_text("📁 No workspace available. Please try /link your-email@example.com")
        return

    await _process_and_index_document(
        update=update,
        context=context,
        file_id=photo.file_id,
        file_name=file_name,
        file_size=photo.file_size or 0,
        file_type=file_type,
        file_ext=file_ext,
        workspace=workspace,
    )


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    doc = update.message.document
    if not doc:
        return

    file_name = doc.file_name or "document.pdf"
    file_ext = Path(file_name).suffix.lower()
    file_type = file_ext.lstrip(".")

    if file_ext not in SUPPORTED_EXTENSIONS:
        await update.message.reply_text(
            f"❌ File format `{file_ext}` is not supported.\n\n"
            "Supported formats: PDF (`.pdf`), Word (`.docx`, `.doc`), PowerPoint (`.pptx`, `.ppt`), Excel/CSV (`.xlsx`, `.xls`, `.csv`), Text (`.txt`, `.md`).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    session = get_session(update.effective_user.id)

    # If the user is not linked to an email, ask for their Gmail / email first
    if not tg_user.user_id or not tg_user.email:
        session["pending_doc"] = {
            "file_id": doc.file_id,
            "file_name": file_name,
            "file_size": doc.file_size or 0,
            "file_type": file_type,
            "file_ext": file_ext,
        }
        session["state"] = ConversationState.WAITING_EMAIL
        await update.message.reply_text(
            f"📄 Received *{file_name}*!\n\n"
            "📧 *Please enter your Gmail / email address to link your workspace:*\n\n"
            "*(Once you enter your email, this document will be automatically chunked and indexed so you can ask any question from it!)*",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # User is already linked - get workspace and process
    workspace = await _get_current_workspace(update.effective_user.id, session)
    if workspace is None:
        await update.message.reply_text(
            "📁 No workspace available. Please try /link your-email@example.com",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await _process_and_index_document(
        update=update,
        context=context,
        file_id=doc.file_id,
        file_name=file_name,
        file_size=doc.file_size or 0,
        file_type=file_type,
        file_ext=file_ext,
        workspace=workspace,
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        return

    text = update.message.text.strip()

    clean_text = text.strip()

    # Intercept Reply Keyboard Buttons
    if clean_text in ["📤 Upload PDF", "📤 Upload Document", "Upload PDF", "Upload Document"] or "Upload" in clean_text:
        await upload_handler(update, context)
        return
    elif clean_text in ["📥 Download PDF", "Download PDF"] or "Download" in clean_text:
        await download_handler(update, context)
        return
    elif clean_text in ["❓ Ask Question", "Ask Question"] or "Ask Question" in clean_text:
        set_session(update.effective_user.id, state=ConversationState.WAITING_QUESTION)
        await update.message.reply_text(
            "🧠 *Ask your question! I am ready to answer from your documents.*",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    elif clean_text in ["📝 Summary", "Summary"] or clean_text.endswith("Summary"):
        await summary_handler(update, context)
        return
    elif clean_text in ["⭐ Important Questions", "Important Questions"] or "Important Questions" in clean_text:
        await important_questions_handler(update, context)
        return
    elif clean_text in ["📋 PYQs", "PYQs"] or "PYQ" in clean_text:
        await pyq_handler(update, context)
        return
    elif clean_text in ["🧪 Generate Quiz", "Generate Quiz"] or "Quiz" in clean_text:
        await quiz_handler(update, context)
        return
    elif clean_text in ["📚 Subjects", "Subjects"] or "Subjects" in clean_text:
        await subjects_handler(update, context)
        return
    elif clean_text in ["❓ Help", "Help"] or clean_text.endswith("Help"):
        await help_handler(update, context)
        return

    session = get_session(update.effective_user.id)

    # Check if input is an email address
    is_email = bool(re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', text))
    if session.get("state") == ConversationState.WAITING_EMAIL or is_email:
        if not is_email:
            await update.message.reply_text(
                "❌ Please enter a valid email address (e.g. `yourname@gmail.com`).",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        session["state"] = ConversationState.IDLE
        email = text.lower()
        tg_user = await _link_telegram_user_to_email(update.effective_user.id, email)
        workspace = await _get_current_workspace(update.effective_user.id, session)

        pending_doc = session.pop("pending_doc", None)
        if pending_doc and workspace:
            await update.message.reply_text(
                f"✅ Account linked to *{email}*!\n\n"
                f"⏳ Now chunking and indexing *{pending_doc['file_name']}*...",
                parse_mode=ParseMode.MARKDOWN,
            )
            await _process_and_index_document(
                update=update,
                context=context,
                file_id=pending_doc["file_id"],
                file_name=pending_doc["file_name"],
                file_size=pending_doc["file_size"],
                file_type=pending_doc["file_type"],
                file_ext=pending_doc["file_ext"],
                workspace=workspace,
            )
            return

        ws_name = workspace.name if workspace else "Default"
        await update.message.reply_text(
            f"✅ Telegram account linked to *{email}*!\n"
            f"📁 Workspace: *{ws_name}*\n\n"
            "You can now send any document (PDF, Word, PPT, Excel, etc.) to index it, or ask any question!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return

    state = session.get("state")
    if state == ConversationState.WAITING_QUESTION:
        session["state"] = ConversationState.IDLE
        await _do_answer_question(update, context, text, mode="qa", answer_style="detailed")
        return

    if state == ConversationState.WAITING_SUMMARY_INPUT:
        session["state"] = ConversationState.IDLE
        from services.summarization.source_detector import detect_source_type
        detected = detect_source_type(content=text, url=None, document_id=None, input_type="auto")
        if detected["source_type"] in ["youtube", "url"]:
            await _do_summarize(update, context, text)
        else:
            await _do_answer_question(
                update, context,
                f"Write a thorough, structured summary of the documents regarding: {text}",
                mode="summary", answer_style="detailed"
            )
        return

    if state == ConversationState.WAITING_IMP_QUESTIONS:
        session["state"] = ConversationState.IDLE
        topic = "all uploaded documents" if text.lower() == "all" else text
        await _do_answer_question(
            update, context,
            f"Extract and list the top 10 most important exam questions regarding {topic} based on the documents. For each question, explain key concepts and provide an outline of the answer.",
            mode="qa", answer_style="detailed"
        )
        return

    if state == ConversationState.WAITING_PYQ_INPUT:
        session["state"] = ConversationState.IDLE
        topic = "all uploaded documents" if text.lower() == "all" else text
        await _do_answer_question(
            update, context,
            f"List previous year university exam questions (PYQs) and frequent exam questions on {topic} from the documents, along with mark allocations and key points to cover in answers.",
            mode="qa", answer_style="detailed"
        )
        return

    if state == ConversationState.WAITING_QUIZ_INPUT:
        session["state"] = ConversationState.IDLE
        topic = "all uploaded documents" if text.lower() == "all" else text
        await _do_answer_question(
            update, context,
            f"Generate a 5-question multiple choice quiz (MCQ) on {topic} based strictly on the documents. For each question, provide 4 options (A, B, C, D) and explain the correct answer at the end.",
            mode="quiz", answer_style="detailed"
        )
        return

    # Auto-detect URLs and YouTube links to summarize them automatically
    from services.summarization.source_detector import detect_source_type
    detected = detect_source_type(content=text, url=None, document_id=None, input_type="auto")
    if detected["source_type"] in ["youtube", "url"]:
        await _do_summarize(update, context, text)
        return

    # Direct answer for any standard question
    await _do_answer_question(update, context, text, mode="qa", answer_style="detailed")


async def _get_current_workspace(telegram_id: int, session: dict) -> Optional[Workspace]:
    if session.get("workspace_id"):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Workspace).where(Workspace.id == session["workspace_id"]))
            workspace = result.scalars().first()
            if workspace:
                return workspace
    workspace = await _get_linked_workspace(telegram_id)
    if workspace:
        return workspace

    async with AsyncSessionLocal() as db:
        tg_res = await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))
        tg_user = tg_res.scalars().first()
        if tg_user and tg_user.user_id:
            ws_res = await db.execute(
                select(Workspace).where(Workspace.owner_id == tg_user.user_id).order_by(Workspace.created_at.asc())
            )
            ws = ws_res.scalars().first()
            if ws:
                tg_user.workspace_id = ws.id
                await db.commit()
                session["workspace_id"] = ws.id
                return ws

    return await _get_default_workspace()


async def _list_workspace_documents(workspace_id: int) -> list[Document]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document)
            .where(Document.workspace_id == workspace_id, Document.status == "ready")
            .order_by(Document.created_at.desc())
        )
        return result.scalars().all()


async def _list_admin_documents() -> list[Document]:
    """Return all ready documents uploaded by admins (user 1, 15, or role == 'admin')."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document)
            .join(Workspace, Document.workspace_id == Workspace.id)
            .join(User, Workspace.owner_id == User.id)
            .where((User.role == "admin") | (User.id.in_([1, 15])), Document.status == "ready")
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())


async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = await _register_user(update)
    if not tg_user:
        return

    # List documents from admin workspaces and the user's workspace
    documents = await _list_admin_documents()
    session = get_session(update.effective_user.id)
    workspace = await _get_current_workspace(update.effective_user.id, session)
    if workspace:
        user_docs = await _list_workspace_documents(workspace.id)
        seen = {d.id for d in documents}
        for ud in user_docs:
            if ud.id not in seen:
                documents.append(ud)
                seen.add(ud.id)

    if not documents:
        await update.message.reply_text(
            "📁 No PDFs are available yet. Upload documents from the website or send a PDF here.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    items = [{"id": d.id, "original_name": d.original_filename} for d in documents]
    await update.message.reply_text(
        f"📄 *{len(items)} PDF(s) available*\n\nChoose one to download:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=pdf_list_keyboard(items),
    )


async def _process_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    question: str,
    subject_id: Optional[int],
    mode: str,
):
    """Answer the question directly via the RAG pipeline."""
    if not question or not question.strip():
        await update.message.reply_text("Please send a non-empty question.")
        return

    await _do_answer_question(
        update=update,
        context=context,
        question=question.strip(),
        mode=mode or "qa",
        answer_style="detailed",
    )
async def _do_answer_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    question: str,
    mode: str,
    answer_style: str,  # "short" or "detailed"
):
    """Run the RAG pipeline and send the answer."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    # Initialize target_msg for progressive streaming updates
    target_msg = update.callback_query.message if (update.callback_query and update.callback_query.message) else None
    if not target_msg:
        target_msg = await update.effective_message.reply_text("⏳ *Searching documents...*", parse_mode=ParseMode.MARKDOWN)

    session = get_session(update.effective_user.id)
    workspace = await _get_current_workspace(update.effective_user.id, session)
    if workspace is None:
        await target_msg.edit_text(
            "📁 No workspace linked. Use /link your-email@example.com and then /subjects.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if mode != "qa":
        question = f"Please answer in {mode} mode:\n{question}"

    # Get documents for user workspace and admin workspaces
    user_docs = await _list_workspace_documents(workspace.id)
    admin_docs = await _list_admin_documents()

    # Match if question specifically names or references a document
    matched_doc = _match_document_in_query(question, user_docs)
    if not matched_doc:
        matched_doc = _match_document_in_query(question, admin_docs)

    from services import vector_store, ollama_client
    from services.rag_engine import _build_rag_prompt, _keyword_rerank

    top_k = 3 if answer_style == "short" else settings.TOP_K_RETRIEVAL
    RELEVANCE_THRESHOLD = 1.2 if answer_style == "short" else 1.0

    filtered_results = []

    if matched_doc:
        target_ws = matched_doc.workspace_id
        target_names = {matched_doc.original_filename, matched_doc.filename}

        # Search FAISS specifically in the matched document's workspace
        raw_results = vector_store.search(target_ws, question, top_k=30)
        doc_results = [(d, s) for d, s in raw_results if d.metadata.get("filename") in target_names]

        # Check if the query is an overview / abstract / summary query
        is_overview = bool(re.search(
            r'\b(abstract|summary|summarize|overview|tell me about|what is|describe|introduction|intro|objective|who wrote|author|paper)\b',
            question.lower()
        ))

        if is_overview:
            store = vector_store._get_store(target_ws)
            early_chunks = []
            if store:
                for ch in store.docstore._dict.values():
                    if ch.metadata.get("filename") in target_names:
                        idx = ch.metadata.get("chunk_index", 999)
                        if idx in (0, 1, 2, 3, 4):
                            early_chunks.append((ch, 0.05 * idx))
                early_chunks.sort(key=lambda x: x[0].metadata.get("chunk_index", 0))

            seen = set()
            for ch, sc in early_chunks + doc_results:
                if ch.page_content not in seen:
                    seen.add(ch.page_content)
                    filtered_results.append((ch, sc))
            filtered_results = filtered_results[:top_k * 2]
        else:
            filtered_results = doc_results[:top_k * 2]

    else:
        # No specific doc mentioned:
        # Search BOTH the user's workspace AND all admin workspaces together!
        admin_ws_ids = list({d.workspace_id for d in admin_docs})
        search_ws_ids = list(set([workspace.id] + admin_ws_ids))

        raw_results = vector_store.search(search_ws_ids, question, top_k=30)
        raw_results = _keyword_rerank(raw_results, question)

        # Pick the single best matching document across both workspaces
        if raw_results:
            from collections import defaultdict
            doc_scores: dict[str, list[float]] = defaultdict(list)
            for doc, score in raw_results[:15]:
                fname = doc.metadata.get("filename", "Unknown")
                doc_scores[fname].append(score)

            best_doc_name = min(doc_scores, key=lambda f: sum(doc_scores[f]) / len(doc_scores[f]))
            filtered_results = [
                (doc, score) for doc, score in raw_results
                if doc.metadata.get("filename") == best_doc_name
            ][:top_k * 2]

    # No results found
    if not filtered_results:
        await target_msg.edit_text(
            "❌ *Answer not available*\n\n"
            "The answer to your question was not found in any uploaded document. "
            "Please upload a relevant document first.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Determine workspace type for the right system prompt
    workspace_type = "student"
    if workspace:
        ws_name = (workspace.name or "").lower()
        if "business" in ws_name or "analytics" in ws_name:
            workspace_type = "business"

    # Build prompt using the standard RAG pipeline
    system, assistant_context, user_prompt = _build_rag_prompt(question, filtered_results, workspace_type)

    # Use configured default LLM model (gemma4:12b)
    model = settings.DEFAULT_LLM_MODEL

    import time
    import re as _re

    # Build sources list
    sources = []
    seen = set()
    for doc, _ in filtered_results:
        name = doc.metadata.get("filename", "Unknown")
        if name not in seen:
            seen.add(name)
            item = {"document_name": name}
            if doc.metadata.get("page_number") is not None:
                item["page_number"] = doc.metadata["page_number"]
            sources.append(item)

    source_text = ""
    if sources:
        source_text = "\n".join(
            f"- {s.get('document_name', 'Unknown')}" + (f" (p.{s['page_number']})" if s.get('page_number') else "")
            for s in sources
        )

    # Indicate thinking
    try:
        await target_msg.edit_text("🧠 *Thinking & generating answer...*", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass

    # Stream tokens live into Telegram so the user sees real-time progress word-by-word
    full_answer = ""
    last_edit = time.time()
    last_len = 0

    # Increased token limits: 1024 for short answers, 2560 for detailed answers
    token_limit = 1024 if answer_style == "short" else 2560

    async for token in ollama_client.chat_stream(
        prompt=user_prompt,
        system=system,
        model=model,
        temperature=0.1 if answer_style == "short" else 0.7,
        max_tokens=token_limit,
    ):
        full_answer += token
        now = time.time()
        # Edit message every 2.0s if at least 35 new characters arrived to strictly avoid Telegram flood limits
        if now - last_edit >= 2.0 and len(full_answer.strip()) >= last_len + 35:
            last_edit = now
            last_len = len(full_answer.strip())
            display_text = _clean_leaked_prompts(full_answer.strip())
            if display_text:
                try:
                    preview_text = display_text[:4000] + " ▌"
                    await target_msg.edit_text(preview_text)
                except RetryAfter as e:
                    last_edit = now + e.retry_after + 1.0
                except Exception:
                    pass

    # Final cleanup of answer
    clean_ans = _clean_leaked_prompts(full_answer.strip())
    if not clean_ans:
        clean_ans = full_answer.strip()

    q_lower = question.lower()
    _is_detail_query = bool(_re.search(
        r'\b(abstract|education|certificate|skill|experience|project|contact|address|email|phone|language|achievement|declaration|objective|profile|tell me about|summarize|summary|overview|describe)\b',
        q_lower
    ))

    if answer_style == "short" and not _is_detail_query:
        clean_ans = _truncate_to_sentences(clean_ans, max_sentences=5)

    not_found = "not found" in clean_ans.lower()
    if source_text and not not_found:
        final_message = f"{clean_ans}\n\n📚 *Sources:*\n{source_text}"
    else:
        final_message = clean_ans

    # Final render - if longer than 4000 characters, use _send_long
    if len(final_message) > 4000:
        try:
            await target_msg.edit_text("✅ *Answer generated:*", parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        await _send_long(target_msg, final_message)
    else:
        try:
            await target_msg.edit_text(final_message, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await target_msg.edit_text(final_message, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
            except Exception:
                await target_msg.edit_text(final_message, disable_web_page_preview=True)
        except Exception:
            try:
                await target_msg.edit_text(final_message, disable_web_page_preview=True)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await target_msg.edit_text(final_message, disable_web_page_preview=True)
                except Exception:
                    await _send_long(target_msg, final_message)
            except Exception:
                await _send_long(target_msg, final_message)

    if workspace and session.get("user_id"):
        await _save_chat_history(session["user_id"], workspace.id, question, clean_ans, sources)
