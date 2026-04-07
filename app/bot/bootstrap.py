from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.ai.agent import FinanceAgent
from app.bot.handlers.callbacks import handle_callback
from app.bot.handlers.commands import cmd_clear, cmd_help, cmd_settings, cmd_sheet, handle_message
from app.bot.handlers.onboarding import build_onboarding_handler
from app.bot.media import handle_document, handle_photo, handle_voice
from app.bot.state import log, runtime_state, set_agent, sheets
from app.core import config
from app.services.scheduler_service import register_jobs


async def post_init(app: Application) -> None:
    log.info("Connecting to Google Sheets…")
    sheets.connect()

    runtime_state.language = sheets.get_setting("language", runtime_state.language) or config.LANGUAGE
    runtime_state.currency = sheets.get_setting("currency", runtime_state.currency) or config.CURRENCY
    runtime_state.ai_model = sheets.get_setting("ai_model", runtime_state.ai_model) or config.AI_MODEL
    runtime_state.timezone = sheets.get_setting("timezone", runtime_state.timezone) or config.TIMEZONE
    sheets.currency = runtime_state.currency

    agent = FinanceAgent(
        config.OPENROUTER_API_KEY,
        runtime_state.ai_model,
        sheets,
        currency=runtime_state.currency,
        language=runtime_state.language,
    )
    set_agent(agent)
    log.info("Agent initialized ✓")

    if app.job_queue:
        register_jobs(app.job_queue, config, app.bot, sheets, agent)
        log.info("Scheduler configured ✓")

    log.info("Bot ready ✓")


def build_application() -> Application:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(config.TELEGRAM_TOKEN).post_init(post_init).build()

    app.add_handler(build_onboarding_handler())
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("sheet", cmd_sheet))
    app.add_handler(CommandHandler("table", cmd_sheet))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    app = build_application()
    log.info("Starting polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
