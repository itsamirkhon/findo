from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import settings_keyboard, settings_summary
from app.bot.state import allowed, get_agent, log
from app.bot.streaming import stream_text_reply


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not allowed(query.from_user.id):
        return

    if query.data and query.data.startswith("settings:"):
        parts = query.data.split(":")
        action = parts[1] if len(parts) > 1 else "open"

        if action in {"refresh", "open"}:
            await query.message.reply_text(
                settings_summary(),
                parse_mode="Markdown",
                reply_markup=settings_keyboard(),
            )
            return

        if action == "language":
            await query.message.reply_text(
                "🌐 Введи язык следующим сообщением (например: `ru`, `en`, `uz`, `es`, `fr`):",
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "language"
            return

        if action == "currency":
            await query.message.reply_text(
                "💱 Введи валюту (например `EUR`, `USD`, `RUB`) следующим сообщением:",
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "currency"
            return

        if action == "ai_model":
            await query.message.reply_text(
                "🧠 Введи ID модели OpenRouter следующим сообщением:\n`google/gemini-3.1-flash-lite-preview`",
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "ai_model"
            return

        if action == "timezone":
            await query.message.reply_text(
                "🕒 Введи таймзону (например `Europe/Moscow`, `Asia/Tashkent`) следующим сообщением:",
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "timezone"
            return

    await ctx.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    prompts = {
        "dashboard": "Верни текущий дашборд",
        "plan": "Сравни план с фактом за этот месяц",
        "stats": "Дай подробную статистику за текущий месяц",
    }
    prompt = prompts.get(query.data, "Помоги")

    await stream_text_reply(
        query.message,
        get_agent().process_stream(prompt),
        empty_text="❌ Пустой ответ.",
        error_text="❌ Ошибка при генерации ответа.",
    )
