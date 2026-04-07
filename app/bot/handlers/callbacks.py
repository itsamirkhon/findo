from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import settings_keyboard, settings_summary
from app.bot.state import (
    allowed,
    get_agent,
    histories,
    is_english,
    log,
    reset_runtime_settings_to_defaults,
    sheets,
)
from app.bot.streaming import stream_text_reply


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not allowed(query.from_user.id):
        return

    if query.data and query.data.startswith("clear:"):
        parts = query.data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        owner_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

        if owner_id is not None and query.from_user.id != owner_id:
            await query.message.reply_text(
                "⚠️ Only the user who requested the reset can confirm it."
                if is_english()
                else "⚠️ Подтвердить сброс может только тот пользователь, который его запросил."
            )
            return

        if action == "cancel":
            await query.message.reply_text(
                "✅ Reset cancelled." if is_english() else "✅ Сброс отменён."
            )
            return

        if action == "confirm":
            sheets.reset_all_data()
            histories.clear()
            ctx.application.user_data.clear()
            ctx.application.chat_data.clear()
            reset_runtime_settings_to_defaults()
            await query.message.reply_text(
                (
                    "🧹 Everything was reset.\n\nThe spreadsheet, chat memory, budget data, and custom settings were cleared. The bot is back to a fresh state."
                )
                if is_english()
                else "🧹 Всё было очищено.\n\nТаблица, память чата, бюджетные данные и кастомные настройки сброшены. Бот снова в состоянии с нуля."
            )
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
                (
                    "🌐 Send the language in the next message (for example: `en`, `ru`, `uz`, `es`, `fr`):"
                    if is_english()
                    else "🌐 Введи язык следующим сообщением (например: `ru`, `en`, `uz`, `es`, `fr`):"
                ),
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "language"
            return

        if action == "currency":
            await query.message.reply_text(
                (
                    "💱 Send the currency in the next message (for example `EUR`, `USD`, `GBP`):"
                    if is_english()
                    else "💱 Введи валюту (например `EUR`, `USD`, `RUB`) следующим сообщением:"
                ),
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "currency"
            return

        if action == "ai_model":
            await query.message.reply_text(
                (
                    "🧠 Send the OpenRouter model ID in the next message:\n`google/gemini-3.1-flash-lite-preview`"
                    if is_english()
                    else "🧠 Введи ID модели OpenRouter следующим сообщением:\n`google/gemini-3.1-flash-lite-preview`"
                ),
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "ai_model"
            return

        if action == "timezone":
            await query.message.reply_text(
                (
                    "🕒 Send the timezone in the next message (for example `Europe/London`, `Europe/Berlin`):"
                    if is_english()
                    else "🕒 Введи таймзону (например `Europe/Moscow`, `Asia/Tashkent`) следующим сообщением:"
                ),
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "timezone"
            return

    await ctx.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    prompts = {
        "dashboard": "Show the current dashboard" if is_english() else "Верни текущий дашборд",
        "plan": "Compare plan vs actual for this month" if is_english() else "Сравни план с фактом за этот месяц",
        "stats": "Give detailed statistics for the current month" if is_english() else "Дай подробную статистику за текущий месяц",
    }
    prompt = prompts.get(query.data, "Help me" if is_english() else "Помоги")

    await stream_text_reply(
        query.message,
        get_agent().process_stream(prompt),
        empty_text="❌ Empty response." if is_english() else "❌ Пустой ответ.",
        error_text="❌ Error while generating the response." if is_english() else "❌ Ошибка при генерации ответа.",
    )
