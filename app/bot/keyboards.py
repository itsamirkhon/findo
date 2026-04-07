from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.runtime import runtime_settings as runtime_state
from app.bot.state import sheets


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
