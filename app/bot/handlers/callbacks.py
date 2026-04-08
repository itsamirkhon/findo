from __future__ import annotations

import datetime

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers.commands import (
    help_text,
    payment_detail_text,
    payments_list_keyboard,
    payments_manager_text,
    settings_summary_text,
)
from app.bot.handlers.onboarding import begin_forced_onboarding
from app.bot.keyboards import category_keyboard, payment_item_keyboard, reminder_keyboard, settings_keyboard
from app.bot.state import (
    allowed,
    get_agent,
    histories,
    reset_runtime_settings_to_defaults,
    sheets,
)
from app.bot.streaming import stream_text_reply
from app.services.sheets_service import CATEGORY_LABELS


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not allowed(query.from_user.id):
        return

    data = query.data or ""

    if data.startswith("clear:"):
        await _handle_clear_callback(query, ctx)
        return

    if data.startswith("settings:"):
        await _handle_settings_callback(query, ctx)
        return

    if data.startswith("payments:") or data.startswith("payment:"):
        await _handle_payments_callback(query, ctx)
        return

    if data == "info:open":
        await query.message.reply_text(help_text(), parse_mode="Markdown")
        return

    await ctx.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    prompts = {
        "dashboard": "Show the current dashboard",
        "plan": "Compare plan vs actual for this month",
        "stats": "Give detailed statistics for the current month",
    }
    prompt = prompts.get(data, "Help me")

    await stream_text_reply(
        query.message,
        get_agent().process_stream(prompt),
        empty_text="❌ Empty response.",
        error_text="❌ Error while generating the response.",
    )


async def _handle_clear_callback(query, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    parts = (query.data or "").split(":")
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


async def _handle_settings_callback(query, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    parts = (query.data or "").split(":")
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


async def _handle_payments_callback(query, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    data = query.data or ""
    if data == "payments:cancel":
        _clear_payments_pending(ctx.user_data)
        await _cleanup_payments_step_messages(
            ctx,
            query.message.chat_id,
            ctx.user_data,
            current_message_id=query.message.message_id,
        )
        sent = await query.message.reply_text(
            payments_manager_text(),
            parse_mode="Markdown",
            reply_markup=payments_list_keyboard(),
        )
        ctx.user_data["payments_prompt_message_id"] = sent.message_id
        return

    if data == "payments:open":
        _clear_payments_pending(ctx.user_data)
        stale_step_prompt_id = ctx.user_data.pop("payments_step_prompt_message_id", None)
        stale_manager_prompt_id = ctx.user_data.pop("payments_prompt_message_id", None)
        for message_id in (stale_step_prompt_id, stale_manager_prompt_id):
            if not isinstance(message_id, int):
                continue
            try:
                await ctx.bot.delete_message(chat_id=query.message.chat_id, message_id=message_id)
            except Exception:
                pass
        try:
            await ctx.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
        except Exception:
            pass
        sent = await query.message.reply_text(
            payments_manager_text(),
            parse_mode="Markdown",
            reply_markup=payments_list_keyboard(),
        )
        ctx.user_data["payments_prompt_message_id"] = sent.message_id
        return

    if data == "payments:close":
        _clear_payments_pending(ctx.user_data)
        await _cleanup_payments_messages(
            ctx,
            query.message.chat_id,
            ctx.user_data,
            current_message_id=query.message.message_id,
        )
        return

    if data == "payments:add":
        _clear_payments_pending(ctx.user_data)
        ctx.user_data["payments_pending_action"] = "name"
        ctx.user_data["payments_draft"] = {}
        sent = await query.message.reply_text(
            "📝 Send the payment name in the next message.\nExample: `Apartment rent`",
            parse_mode="Markdown",
        )
        ctx.user_data["payments_step_prompt_message_id"] = sent.message_id
        return

    if data.startswith("payments:view:"):
        payment_id = data.split(":", 2)[2]
        payment = sheets.get_expected_payment(payment_id)
        if not payment:
            await query.message.reply_text("❌ Expected payment not found.")
            return
        await query.message.reply_text(
            payment_detail_text(payment),
            parse_mode="Markdown",
            reply_markup=payment_item_keyboard(payment["id"], payment["active"]),
        )
        return

    if data.startswith("payments:edit:"):
        payment_id = data.split(":", 2)[2]
        payment = sheets.get_expected_payment(payment_id)
        if not payment:
            await query.message.reply_text("❌ Expected payment not found.")
            return
        ctx.user_data["payments_edit_id"] = payment_id
        ctx.user_data["payments_draft"] = {
            "name": payment["name"],
            "amount": payment["amount"],
            "due_day": payment["due_day"],
            "category": payment["category"],
        }
        ctx.user_data["payments_pending_action"] = "name"
        sent = await query.message.reply_text(
            "✏️ Editing payment.\nSend the new payment name in the next message.",
            parse_mode="Markdown",
        )
        ctx.user_data["payments_step_prompt_message_id"] = sent.message_id
        return

    if data.startswith("payments:toggle:"):
        payment_id = data.split(":", 2)[2]
        payment = sheets.get_expected_payment(payment_id)
        if not payment:
            await query.message.reply_text("❌ Expected payment not found.")
            return
        updated = sheets.update_expected_payment(payment_id, active=not payment["active"])
        if not updated:
            await query.message.reply_text("❌ Could not update expected payment.")
            return
        await query.message.reply_text(
            payment_detail_text(updated),
            parse_mode="Markdown",
            reply_markup=payment_item_keyboard(updated["id"], updated["active"]),
        )
        return

    if data.startswith("payments:delete:"):
        payment_id = data.split(":", 2)[2]
        deleted = sheets.delete_expected_payment(payment_id)
        await query.message.reply_text("✅ Expected payment deleted." if deleted else "❌ Expected payment not found.")
        return

    if data.startswith("payments:category:"):
        category = data.split(":", 2)[2]
        canonical_category = sheets._canonical_category(category)
        if canonical_category not in CATEGORY_LABELS["en"]:
            await query.message.reply_text("❌ Unknown category.")
            return
        draft = ctx.user_data.setdefault("payments_draft", {})
        draft["category"] = canonical_category
        payment_id = ctx.user_data.get("payments_edit_id")
        if payment_id:
            payment = sheets.update_expected_payment(payment_id, **draft)
            action_text = "updated"
        else:
            payment = sheets.create_expected_payment(**draft)
            action_text = "created"
        _clear_payments_pending(ctx.user_data)
        await _cleanup_payments_messages(
            ctx,
            query.message.chat_id,
            ctx.user_data,
            current_message_id=query.message.message_id,
        )
        if not payment:
            await query.message.reply_text("❌ Could not save expected payment.")
            return
        await query.message.reply_text(
            f"✅ Expected payment {action_text}.\n\n{payment_detail_text(payment)}",
            parse_mode="Markdown",
            reply_markup=payment_item_keyboard(payment["id"], payment["active"]),
        )
        return

    if data.startswith("payment:paid:"):
        _, _, payment_id, month = data.split(":", 3)
        payment = sheets.get_expected_payment(payment_id)
        if not payment:
            await query.message.reply_text("❌ Expected payment not found.")
            return
        sheets.mark_payment_paid(payment_id, month)
        await query.message.reply_text(
            f"✅ Marked as paid for {month}: *{payment['name']}*",
            parse_mode="Markdown",
        )
        return

    if data.startswith("payment:snooze:"):
        _, _, payment_id, month = data.split(":", 3)
        payment = sheets.get_expected_payment(payment_id)
        if not payment:
            await query.message.reply_text("❌ Expected payment not found.")
            return
        status = sheets.snooze_payment(payment_id, month, days=1)
        await query.message.reply_text(
            f"⏰ Snoozed until `{status['snooze_until']}` for *{payment['name']}*",
            parse_mode="Markdown",
        )


def build_payment_reminder_text(payment: dict, month: str) -> str:
    category = CATEGORY_LABELS["en"].get(payment["category"], payment["category"])
    timing = sheets.due_timing_label(payment["due_day"])
    due_date = sheets.get_due_date(payment["due_day"], month)
    return (
        "🔔 *Expected payment reminder*\n\n"
        f"*Name:* `{payment['name']}`\n"
        f"*Amount:* `{payment['amount']:.2f} {payment['currency']}`\n"
        f"*Category:* `{category}`\n"
        f"*Due date:* `{due_date.isoformat()}`\n"
        f"*Status:* `{timing}`"
    )


def _clear_payments_pending(user_data: dict) -> None:
    for key in ("payments_pending_action", "payments_edit_id", "payments_draft"):
        user_data.pop(key, None)


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


async def _cleanup_payments_messages(
    ctx: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_data: dict,
    current_message_id: int | None = None,
) -> None:
    message_ids: list[int] = []
    for key in ("payments_request_message_id", "payments_prompt_message_id", "payments_step_prompt_message_id"):
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


async def _cleanup_payments_step_messages(
    ctx: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_data: dict,
    current_message_id: int | None = None,
) -> None:
    message_ids: list[int] = []
    message_id = user_data.pop("payments_step_prompt_message_id", None)
    if isinstance(message_id, int):
        message_ids.append(message_id)
    if current_message_id:
        message_ids.append(current_message_id)

    for message_id in dict.fromkeys(message_ids):
        try:
            await ctx.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
