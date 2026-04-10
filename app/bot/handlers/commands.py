from __future__ import annotations

import csv
import datetime
import io

import pytz
from telegram import InputFile
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers.onboarding import continue_forced_onboarding
from app.bot.keyboards import (
    category_keyboard,
    clear_confirmation_keyboard,
    export_period_keyboard,
    payment_item_keyboard,
    payments_manager_keyboard,
    settings_keyboard,
)
from app.bot.state import allowed, apply_runtime_setting, histories, sheets
from app.bot.streaming import reply_agent_stream
from app.services.sheets_service import CATEGORY_LABELS, GREEN_ZONE_CATEGORIES, RED_ZONE_CATEGORIES, YELLOW_ZONE_CATEGORIES

EXPORT_HEADERS = ["date", "type", "amount", "category", "description", "currency", "week", "month", "quarter", "half_year", "year", "added_at"]


def help_text() -> str:
    return (
        "🤖 *Available Commands*\n\n"
        "/start   — main menu\n"
        "/sheet   — Google Sheets link\n"
        "/table   — Google Sheets link\n"
        "/export  — export transactions CSV\n"
        "/settings — bot settings\n"
        "/payments — expected payments manager\n"
        "/analytics — advanced AI financial analytics\n"
        "/goals   — saving goals (Копилки)\n"
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


async def cmd_analytics(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = (
        "Пользователь запросил глубокую финансовую аналитику. ПРОАНАЛИЗИРУЙ данные (используй get_stats_by_month для "
        "текущего и прошлого месяцев для сравнения). Сравни траты по категориям, найди АНОМАЛИИ "
        "(сильный рост расходов), оцени выполнение плана и дай 2-3 практичных совета по оптимизации."
    )
    await reply_agent_stream(update, prompt)


async def cmd_goals(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = (
        "Пользователь вызвал /goals. Покажи все его Копилки (используй get_saving_goals). "
        "Для каждой цели покажи: имя, прогресс (saved/target), процент, дедлайн и правило автонакопления если есть. "
        "Если копилок нет, предложи создать первую."
    )
    await reply_agent_stream(update, prompt)


async def cmd_sheet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    text = f"📁 Your spreadsheet:\n{sheets.get_spreadsheet_url()}"
    await update.message.reply_text(text)


def _parse_tx_date(raw: str) -> datetime.date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        return None


def _records_between(start: datetime.date, end: datetime.date) -> list[dict]:
    records = sheets.list_transactions(month=None)
    result: list[dict] = []
    for item in records:
        tx_date = _parse_tx_date(item.get("date", ""))
        if tx_date is None:
            continue
        if start <= tx_date <= end:
            result.append(item)
    return result


def build_export_payload_for_action(action: str) -> tuple[list[dict], str, str] | None:
    today = datetime.date.today()
    key = (action or "").strip().lower()

    if key == "all":
        return sheets.list_transactions(month=None), "all time", "all"

    if key == "day":
        records = _records_between(today, today)
        suffix = today.strftime("%Y%m%d")
        return records, f"day {today.isoformat()}", f"day_{suffix}"

    if key == "week":
        week_start = today - datetime.timedelta(days=today.weekday())
        week_end = week_start + datetime.timedelta(days=6)
        records = _records_between(week_start, week_end)
        suffix = f"{week_start.strftime('%Y%m%d')}_{week_end.strftime('%Y%m%d')}"
        return records, f"week {week_start.isoformat()}..{week_end.isoformat()}", f"week_{suffix}"

    if key == "month":
        month_key = today.strftime("%Y-%m")
        records = sheets.list_transactions(month=month_key)
        return records, f"month {month_key}", month_key

    if key == "year":
        year_start = datetime.date(today.year, 1, 1)
        year_end = datetime.date(today.year, 12, 31)
        records = _records_between(year_start, year_end)
        return records, f"year {today.year}", f"year_{today.year}"

    quarter_map = {"q1": (1, 3), "q2": (4, 6), "q3": (7, 9), "q4": (10, 12)}
    if key in quarter_map:
        start_month, end_month = quarter_map[key]
        quarter_start = datetime.date(today.year, start_month, 1)
        if end_month == 12:
            quarter_end = datetime.date(today.year, 12, 31)
        else:
            quarter_end = datetime.date(today.year, end_month + 1, 1) - datetime.timedelta(days=1)
        records = _records_between(quarter_start, quarter_end)
        return records, f"{key.upper()} {today.year}", f"{key}_{today.year}"

    return None


def parse_custom_export_range(text: str) -> tuple[datetime.date, datetime.date] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    normalized = raw.replace("..", " ").replace(",", " ")
    normalized = normalized.replace("—", " ").replace(" to ", " ")
    parts = [p for p in normalized.split() if p]
    if len(parts) != 2:
        return None

    def _parse(token: str) -> datetime.date | None:
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.datetime.strptime(token, fmt).date()
            except ValueError:
                continue
        return None

    start = _parse(parts[0])
    end = _parse(parts[1])
    if not start or not end:
        return None
    if start > end:
        start, end = end, start
    return start, end


async def send_export_csv(message, records: list[dict], label: str, suffix: str) -> None:
    if not records:
        await message.reply_text("ℹ️ No transactions found for export.")
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_HEADERS)
    for item in records:
        raw_category = str(item.get("category", "")).strip()
        canonical_category = sheets._canonical_category(raw_category)
        category_en = CATEGORY_LABELS["en"].get(canonical_category, raw_category)
        writer.writerow([
            item.get("date", ""),
            item.get("type", ""),
            item.get("amount", ""),
            category_en,
            item.get("description", ""),
            item.get("currency", ""),
            item.get("week", ""),
            item.get("month", ""),
            item.get("quarter", ""),
            item.get("half_year", ""),
            item.get("year", ""),
            item.get("added_at", ""),
        ])

    csv_bytes = buffer.getvalue().encode("utf-8")
    filename = f"transactions_{suffix}.csv"
    await message.reply_document(
        document=InputFile(io.BytesIO(csv_bytes), filename=filename),
        caption=f"📤 Export generated for {label}. Rows: {len(records)}",
    )


async def cmd_export(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    ctx.user_data.pop("export_pending_action", None)
    await update.message.reply_text(
        "📤 Choose export period:",
        reply_markup=export_period_keyboard(),
    )


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


def _all_expense_categories() -> list[str]:
    return RED_ZONE_CATEGORIES + YELLOW_ZONE_CATEGORIES + GREEN_ZONE_CATEGORIES


def _payment_summary_line(payment: dict) -> str:
    status = "active" if payment.get("active") else "inactive"
    category = CATEGORY_LABELS["en"].get(payment.get("category", ""), payment.get("category", ""))
    return (
        f"• *{payment['name']}* — {payment['amount']:.2f} {payment['currency']} "
        f"on day `{payment['due_day']}` in `{category}` ({status})"
    )


def payments_manager_text() -> str:
    payments = sheets.list_expected_payments(active_only=False)
    if not payments:
        lines = ["No expected payments yet.", "", "Use the button below to add your first one."]
    else:
        lines = ["📌 *Expected Payments*\n"]
        lines.extend(_payment_summary_line(payment) for payment in payments)
        lines.extend(["", "Tap a payment button below to manage it, or add a new one."])
    return "\n".join(lines)


def payment_detail_text(payment: dict) -> str:
    category = CATEGORY_LABELS["en"].get(payment["category"], payment["category"])
    due_date = sheets.get_due_date(payment["due_day"], sheets.current_month_key())
    timing = sheets.due_timing_label(payment["due_day"])
    return (
        "📌 *Expected Payment*\n\n"
        f"*Name:* `{payment['name']}`\n"
        f"*Amount:* `{payment['amount']:.2f} {payment['currency']}`\n"
        f"*Category:* `{category}`\n"
        f"*Due day:* `{payment['due_day']}`\n"
        f"*This month:* `{due_date.isoformat()}`\n"
        f"*Status:* `{'active' if payment['active'] else 'inactive'}`\n"
        f"*Reminder:* `{timing}`"
    )


def payments_list_keyboard() -> "InlineKeyboardMarkup":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for payment in sheets.list_expected_payments(active_only=False):
        icon = "🟢" if payment["active"] else "⚪️"
        rows.append([InlineKeyboardButton(f"{icon} {payment['name']}", callback_data=f"payments:view:{payment['id']}")])
    rows.extend(payments_manager_keyboard().inline_keyboard)
    return InlineKeyboardMarkup(rows)


async def cmd_payments(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        return
    for key in ("payments_pending_action", "payments_edit_id", "payments_draft"):
        ctx.user_data.pop(key, None)
    previous_step_prompt_id = ctx.user_data.pop("payments_step_prompt_message_id", None)
    await _delete_message_safely(ctx, update.effective_chat.id, previous_step_prompt_id)
    ctx.user_data["payments_request_message_id"] = update.message.message_id
    sent = await update.message.reply_text(
        payments_manager_text(),
        parse_mode="Markdown",
        reply_markup=payments_list_keyboard(),
    )
    ctx.user_data["payments_prompt_message_id"] = sent.message_id


async def _delete_message_safely(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await ctx.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _payments_step_transition(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    next_text: str,
    *,
    parse_mode: str | None = None,
    reply_markup=None,
) -> None:
    chat_id = update.effective_chat.id
    previous_prompt_id = ctx.user_data.pop("payments_step_prompt_message_id", None)
    await _delete_message_safely(ctx, chat_id, previous_prompt_id)
    await _delete_message_safely(ctx, chat_id, update.message.message_id)

    sent = await update.message.reply_text(
        next_text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
    ctx.user_data["payments_step_prompt_message_id"] = sent.message_id


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    if await continue_forced_onboarding(update, ctx):
        return

    payments_pending = ctx.user_data.get("payments_pending_action")
    if payments_pending:
        value = (update.message.text or "").strip()
        if not value:
            await update.message.reply_text("❌ Empty value. Please try again.")
            return

        draft = ctx.user_data.setdefault("payments_draft", {})
        try:
            if payments_pending == "name":
                draft["name"] = value
                ctx.user_data["payments_pending_action"] = "amount"
                await _payments_step_transition(
                    update,
                    ctx,
                    "💶 Send the amount in the next message.\nExample: `500`",
                    parse_mode="Markdown",
                )
                return

            if payments_pending == "amount":
                amount = float(value.replace(",", "."))
                if amount <= 0:
                    raise ValueError("Amount must be greater than 0.")
                draft["amount"] = round(amount, 2)
                ctx.user_data["payments_pending_action"] = "due_day"
                await _payments_step_transition(
                    update,
                    ctx,
                    "📅 Send the due day of month in the next message.\nExample: `10`",
                    parse_mode="Markdown",
                )
                return

            if payments_pending == "due_day":
                due_day = int(value)
                if not 1 <= due_day <= 31:
                    raise ValueError("Due day must be between 1 and 31.")
                draft["due_day"] = due_day
                ctx.user_data["payments_pending_action"] = "category"
                await _payments_step_transition(
                    update,
                    ctx,
                    "🏷 Choose the expense category:",
                    reply_markup=category_keyboard(),
                )
                return

            if payments_pending == "category":
                await update.message.reply_text(
                    "🏷 Please choose the category using the buttons below.",
                    reply_markup=category_keyboard(),
                )
                return

        except Exception as exc:
            await update.message.reply_text(f"❌ {exc}")
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

    if ctx.user_data.get("export_pending_action") == "custom_range":
        value = (update.message.text or "").strip()
        if not value:
            await update.message.reply_text("❌ Empty value. Send start and end dates.")
            return
        if value.lower() in {"cancel", "/cancel"}:
            ctx.user_data.pop("export_pending_action", None)
            await update.message.reply_text("✅ Custom export cancelled.")
            return

        date_range = parse_custom_export_range(value)
        if not date_range:
            await update.message.reply_text(
                "❌ Invalid format. Send two dates, e.g. `2026-04-01 2026-04-30` or `01.04.2026 30.04.2026`.",
                parse_mode="Markdown",
            )
            return

        start, end = date_range
        records = _records_between(start, end)
        ctx.user_data.pop("export_pending_action", None)
        suffix = f"custom_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
        await send_export_csv(update.message, records, f"custom {start.isoformat()}..{end.isoformat()}", suffix)
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await reply_agent_stream(update, update.message.text)
