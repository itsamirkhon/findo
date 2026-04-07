from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers.commands import help_text, settings_summary_text
from app.bot.handlers.onboarding import begin_forced_onboarding
from app.bot.keyboards import settings_keyboard
from app.bot.state import (
    allowed,
    get_agent,
    histories,
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
            await query.message.reply_text("⚠️ Only the user who requested the reset can confirm it.")
            return

        if action == "cancel":
            await _cleanup_clear_messages(ctx, query.message.chat_id, ctx.user_data)
            await query.message.reply_text("✅ Reset cancelled.")
            return

        if action == "confirm":
            await _cleanup_clear_messages(ctx, query.message.chat_id, ctx.user_data)
            sheets.reset_all_data()
            histories.pop(query.from_user.id, None)
            ctx.user_data.clear()
            ctx.chat_data.clear()
            reset_runtime_settings_to_defaults()
            await begin_forced_onboarding(query.message, ctx)
            return

    if query.data and query.data.startswith("settings:"):
        parts = query.data.split(":")
        action = parts[1] if len(parts) > 1 else "open"

        if action in {"refresh", "open"}:
            sent = await query.message.reply_text(
                await settings_summary_text(),
                parse_mode="Markdown",
                reply_markup=settings_keyboard(),
            )
            ctx.user_data["settings_prompt_message_id"] = sent.message_id
            return

        if action == "close":
            ctx.user_data.pop("settings_pending", None)
            await _cleanup_settings_messages(
                ctx,
                query.message.chat_id,
                ctx.user_data,
                current_message_id=query.message.message_id,
            )
            return

        if action == "currency":
            await query.message.reply_text(
                "💱 Send the currency in the next message (for example `EUR`, `USD`, `GBP`):",
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "currency"
            return

        if action == "ai_model":
            await query.message.reply_text(
                "🧠 Send the OpenRouter model ID in the next message:\n`google/gemini-3.1-flash-lite-preview`",
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "ai_model"
            return

        if action == "timezone":
            await query.message.reply_text(
                "🕒 Send the timezone in the next message (for example `Europe/London`, `Europe/Berlin`):",
                parse_mode="Markdown",
            )
            ctx.user_data["settings_pending"] = "timezone"
            return

    if query.data == "info:open":
        await query.message.reply_text(help_text(), parse_mode="Markdown")
        return

    await ctx.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    prompts = {
        "dashboard": "Show the current dashboard",
        "plan": "Compare plan vs actual for this month",
        "stats": "Give detailed statistics for the current month",
    }
    prompt = prompts.get(query.data, "Help me")

    await stream_text_reply(
        query.message,
        get_agent().process_stream(prompt),
        empty_text="❌ Empty response.",
        error_text="❌ Error while generating the response.",
    )


async def _cleanup_clear_messages(
    ctx: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_data: dict,
) -> None:
    for key in ("clear_prompt_message_id", "clear_request_message_id"):
        message_id = user_data.pop(key, None)
        if not message_id:
            continue
        try:
            await ctx.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass


async def _cleanup_settings_messages(
    ctx: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_data: dict,
    current_message_id: int | None = None,
) -> None:
    message_ids: list[int] = []
    for key in ("settings_request_message_id", "settings_prompt_message_id"):
        message_id = user_data.pop(key, None)
        if isinstance(message_id, int):
            message_ids.append(message_id)
    if current_message_id:
        message_ids.append(current_message_id)

    for message_id in dict.fromkeys(message_ids):
        try:
            await ctx.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
