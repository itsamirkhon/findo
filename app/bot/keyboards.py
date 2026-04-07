from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.runtime import runtime_settings as runtime_state
from app.bot.state import is_english, sheets


def main_keyboard() -> InlineKeyboardMarkup:
    url = sheets.get_spreadsheet_url()
    if is_english():
        return InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("⚙️ Settings", callback_data="settings:open"),
                InlineKeyboardButton("📁 Open Table", url=url),
            ]]
        )
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("⚙️ Настройки", callback_data="settings:open"),
            InlineKeyboardButton("📁 Открыть таблицу", url=url),
        ]]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🌐 Язык", callback_data="settings:language"),
                InlineKeyboardButton("💱 Валюта", callback_data="settings:currency"),
            ],
            [
                InlineKeyboardButton("🧠 AI модель", callback_data="settings:ai_model"),
                InlineKeyboardButton("🕒 Таймзона", callback_data="settings:timezone"),
            ],
            [InlineKeyboardButton("🔄 Обновить", callback_data="settings:refresh")],
        ]
    )


def settings_summary() -> str:
    return (
        "⚙️ *Текущие настройки*\n\n"
        f"🌐 Язык: `{runtime_state.language}`\n"
        f"💱 Валюта: `{runtime_state.currency}`\n"
        f"🧠 AI модель: `{runtime_state.ai_model}`\n"
        f"🕒 Таймзона: `{runtime_state.timezone}`\n"
    )
