from __future__ import annotations

import pytz
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers.onboarding import continue_forced_onboarding
from app.bot.keyboards import clear_confirmation_keyboard, settings_keyboard
from app.bot.state import allowed, apply_runtime_setting, histories, sheets
from app.bot.streaming import reply_agent_stream


def help_text() -> str:
    return (
        "🤖 *Available Commands*\n\n"
        "/start   — main menu\n"
        "/sheet   — Google Sheets link\n"
        "/table   — Google Sheets link\n"
        "/settings — bot settings\n"
        "/clear   — full reset with confirmation\n"
        "/help    — this help message\n\n"
        "*Example phrases:*\n"
        "💸 “Spent 8.50 on coffee in entertainment”\n"
        "💰 “500 salary for a project”\n"
        "📊 “Show statistics for this month”\n"
        "🎤 Voice messages are supported too\n"
        "🧾 You can send a receipt photo or PDF invoice and I’ll extract the transactions\n\n"
        "*Reset note:*\n"
        "`/clear` wipes the spreadsheet, budget, settings, and chat memory after button confirmation.\n"
    )


async def settings_summary_text() -> str:
    return (
        "⚙️ *Current Settings*\n\n"
        "🌐 Language: `en`\n"
        f"💱 Currency: `{sheets.get_setting('currency', '')}`\n"
        f"🧠 AI Model: `{sheets.get_setting('ai_model', '')}`\n"
        f"🕒 Timezone: `{sheets.get_setting('timezone', '')}`\n"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    await update.message.reply_text(help_text(), parse_mode="Markdown")


async def cmd_sheet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    text = f"📁 Your spreadsheet:\n{sheets.get_spreadsheet_url()}"
    await update.message.reply_text(text)


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    ctx.user_data["clear_request_message_id"] = update.message.message_id
    sent = await update.message.reply_text(
        "⚠️ This will fully reset the bot: chat history, all spreadsheet data, budget plan, and custom settings.\n\nAre you sure?",
        reply_markup=clear_confirmation_keyboard(update.effective_user.id),
    )
    ctx.user_data["clear_prompt_message_id"] = sent.message_id


async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    ctx.user_data["settings_request_message_id"] = update.message.message_id
    sent = await update.message.reply_text(
        await settings_summary_text(),
        parse_mode="Markdown",
        reply_markup=settings_keyboard(),
    )
    ctx.user_data["settings_prompt_message_id"] = sent.message_id


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    if await continue_forced_onboarding(update, ctx):
        return

    pending = ctx.user_data.get("settings_pending")
    if pending:
        value = (update.message.text or "").strip()
        if not value:
            await update.message.reply_text("❌ Empty value. Please try again.")
            return

        key = pending
        try:
            if key == "currency":
                value = value.upper()
                if not (2 <= len(value) <= 6 and value.isalpha()):
                    raise ValueError("Currency must be an alphabetic code, for example EUR")
            elif key == "timezone":
                pytz.timezone(value)
            elif key == "ai_model":
                if len(value) < 3:
                    raise ValueError("Model name is too short")

            sheets.set_setting(key, value)
            apply_runtime_setting(key, value)
            ctx.user_data["settings_pending"] = None

            await update.message.reply_text(
                "✅ Setting updated.\n\n" + await settings_summary_text(),
                parse_mode="Markdown",
                reply_markup=settings_keyboard(),
            )
            return
        except Exception as exc:
            await update.message.reply_text(f"❌ {exc}")
            return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await reply_agent_stream(update, update.message.text)
