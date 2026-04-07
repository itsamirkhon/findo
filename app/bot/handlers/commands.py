from __future__ import annotations

import pytz
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import settings_keyboard, settings_summary
from app.bot.state import allowed, apply_runtime_setting, histories, sheets
from app.bot.streaming import reply_agent_stream


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "🤖 *Доступные команды*\n\n"
        "/start   — главное меню\n"
        "/sheet   — ссылка на Google Sheets\n"
        "/table   — ссылка на Google Sheets\n"
        "/settings — настройки бота\n"
        "/clear   — сбросить историю диалога\n"
        "/help    — эта справка\n\n"
        "*Примеры фраз:*\n"
        "💸 «Потратил 8.50 на кофе из категории развлечений»\n"
        "💰 «500 зарплата за проект»\n"
        "📊 «Покажи статистику за этот месяц»\n"
        "🎤 Голосовые тоже поддерживаются (распознаю и обработаю как текст)\n"
        "🧾 Можно отправить фото чека или PDF-инвойс — распознаю и внесу операции\n",
        parse_mode="Markdown",
    )


async def cmd_sheet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    await update.message.reply_text(f"📁 Твоя таблица:\n{sheets.get_spreadsheet_url()}")


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    histories[update.effective_user.id] = []
    await update.message.reply_text("🗑 История диалога очищена.")


async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        settings_summary(),
        parse_mode="Markdown",
        reply_markup=settings_keyboard(),
    )


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    pending = ctx.user_data.get("settings_pending")
    if pending:
        value = (update.message.text or "").strip()
        if not value:
            await update.message.reply_text("❌ Пустое значение. Попробуй ещё раз.")
            return

        key = pending
        try:
            if key == "language":
                if len(value) < 2 or len(value) > 32:
                    raise ValueError("Язык должен быть от 2 до 32 символов (например: ru, en, uz, es, français)")
            elif key == "currency":
                value = value.upper()
                if not (2 <= len(value) <= 6 and value.isalpha()):
                    raise ValueError("Валюта должна быть буквенным кодом, напр. EUR")
            elif key == "timezone":
                pytz.timezone(value)
            elif key == "ai_model":
                if len(value) < 3:
                    raise ValueError("Слишком короткое имя модели")

            sheets.set_setting(key, value)
            apply_runtime_setting(key, value)
            if key == "language":
                histories[update.effective_user.id] = []
            ctx.user_data["settings_pending"] = None

            await update.message.reply_text(
                "✅ Настройка обновлена.\n\n" + settings_summary(),
                parse_mode="Markdown",
                reply_markup=settings_keyboard(),
            )
            return
        except Exception as exc:
            await update.message.reply_text(f"❌ {exc}")
            return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await reply_agent_stream(update, update.message.text)
