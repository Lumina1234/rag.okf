"""Telegram bot startup and polling integration."""

import asyncio
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from core.config import settings
from telegram_bot.handlers import (
    start_handler,
    help_handler,
    link_handler,
    upload_handler,
    download_handler,
    ask_handler,
    summary_handler,
    important_questions_handler,
    pyq_handler,
    quiz_handler,
    timetable_handler,
    explain_handler,
    vtu_handler,
    subjects_handler,
    callback_handler,
    document_handler,
    message_handler,
    mydocs_handler,
    deletedoc_handler,
    photo_handler,
)


async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "Welcome & register"),
        BotCommand("help", "Show help menu"),
        BotCommand("link", "Link your account by email"),
        BotCommand("download", "Download a PDF uploaded by an admin"),
        BotCommand("upload", "Upload is handled from the website"),
        BotCommand("ask", "Ask a question from your documents"),
        BotCommand("summary", "Generate a summary"),
        BotCommand("important_questions", "Get important questions"),
        BotCommand("pyq", "Browse previous year questions"),
        BotCommand("quiz", "Generate a quiz"),
        BotCommand("timetable", "Generate a study timetable"),
        BotCommand("explain", "Explain a topic simply"),
        BotCommand("vtu", "Get a VTU-style answer"),
        BotCommand("subjects", "List available workspaces"),
        BotCommand("mydocs", "List documents in your workspace"),
        BotCommand("deletedoc", "Delete a document from your workspace"),
    ]
    await application.bot.set_my_commands(commands)


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("link", link_handler))
    app.add_handler(CommandHandler("upload", upload_handler))
    app.add_handler(CommandHandler("download", download_handler))
    app.add_handler(CommandHandler("ask", ask_handler))
    app.add_handler(CommandHandler("summary", summary_handler))
    app.add_handler(CommandHandler("important_questions", important_questions_handler))
    app.add_handler(CommandHandler("pyq", pyq_handler))
    app.add_handler(CommandHandler("quiz", quiz_handler))
    app.add_handler(CommandHandler("timetable", timetable_handler))
    app.add_handler(CommandHandler("explain", explain_handler))
    app.add_handler(CommandHandler("vtu", vtu_handler))
    app.add_handler(CommandHandler("subjects", subjects_handler))
    app.add_handler(CommandHandler("mydocs", mydocs_handler))
    app.add_handler(CommandHandler("deletedoc", deletedoc_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    return app


async def start_polling() -> None:
    app = build_application()
    await app.initialize()
    await app.start()
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()

if __name__ == '__main__':
    import sys
    import os
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    print('Starting Telegram bot (@Rareworlf_bot)...')
    asyncio.run(start_polling())
