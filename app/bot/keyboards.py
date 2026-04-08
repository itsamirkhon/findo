from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.runtime import runtime_settings as runtime_state
from app.bot.state import sheets
from app.services.sheets_service import CATEGORY_LABELS, GREEN_ZONE_CATEGORIES, RED_ZONE_CATEGORIES, YELLOW_ZONE_CATEGORIES


def main_keyboard() -> InlineKeyboardMarkup:
    url = sheets.get_spreadsheet_url()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="settings:open"),
                InlineKeyboardButton("📁 Open Table", url=url),
            ],
            [
                InlineKeyboardButton("ℹ️ Info", callback_data="info:open"),
            ],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💱 Currency", callback_data="settings:currency"),
                InlineKeyboardButton("🧠 AI Model", callback_data="settings:ai_model"),
            ],
            [
                InlineKeyboardButton("🕒 Timezone", callback_data="settings:timezone"),
            ],
            [InlineKeyboardButton("🔄 Refresh", callback_data="settings:refresh")],
            [InlineKeyboardButton("✅ Save and Close", callback_data="settings:close")],
        ]
    )


def payments_manager_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add Payment", callback_data="payments:add"),
                InlineKeyboardButton("📋 Refresh", callback_data="payments:open"),
            ],
            [InlineKeyboardButton("✅ Close", callback_data="payments:close")],
        ]
    )


def payment_item_keyboard(payment_id: str, active: bool) -> InlineKeyboardMarkup:
    toggle_label = "⏸ Deactivate" if active else "▶️ Activate"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ Edit", callback_data=f"payments:edit:{payment_id}"),
                InlineKeyboardButton(toggle_label, callback_data=f"payments:toggle:{payment_id}"),
            ],
            [InlineKeyboardButton("🗑 Delete", callback_data=f"payments:delete:{payment_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="payments:open")],
        ]
    )


def reminder_keyboard(payment_id: str, month: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Mark as Paid", callback_data=f"payment:paid:{payment_id}:{month}"),
                InlineKeyboardButton("⏰ Snooze 1 day", callback_data=f"payment:snooze:{payment_id}:{month}"),
            ],
            [InlineKeyboardButton("📌 Open Payments", callback_data="payments:open")],
        ]
    )


def category_keyboard(prefix: str = "payments:category") -> InlineKeyboardMarkup:
    categories = RED_ZONE_CATEGORIES + YELLOW_ZONE_CATEGORIES + GREEN_ZONE_CATEGORIES
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for category in categories:
        current_row.append(
            InlineKeyboardButton(CATEGORY_LABELS["en"][category], callback_data=f"{prefix}:{category}")
        )
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="payments:cancel")])
    return InlineKeyboardMarkup(rows)


def settings_summary() -> str:
    return (
        "⚙️ *Current Settings*\n\n"
        "🌐 Language: `en`\n"
        f"💱 Currency: `{runtime_state.currency}`\n"
        f"🧠 AI Model: `{runtime_state.ai_model}`\n"
        f"🕒 Timezone: `{runtime_state.timezone}`\n"
    )


def clear_confirmation_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes, reset everything", callback_data=f"clear:confirm:{user_id}"),
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data=f"clear:cancel:{user_id}"),
            ],
        ]
    )


def export_period_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("all", callback_data="export:all"),
                InlineKeyboardButton("day", callback_data="export:day"),
            ],
            [
                InlineKeyboardButton("week", callback_data="export:week"),
                InlineKeyboardButton("month", callback_data="export:month"),
            ],
            [
                InlineKeyboardButton("Year", callback_data="export:year"),
            ],
            [
                InlineKeyboardButton("Q1", callback_data="export:q1"),
                InlineKeyboardButton("Q2", callback_data="export:q2"),
                InlineKeyboardButton("Q3", callback_data="export:q3"),
                InlineKeyboardButton("Q4", callback_data="export:q4"),
            ],
            [
                InlineKeyboardButton("Custom", callback_data="export:custom"),
            ],
        ]
    )
