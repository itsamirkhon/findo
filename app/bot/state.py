from __future__ import annotations

import datetime
import logging

from app.ai.agent import FinanceAgent
from app.core import config
from app.core.runtime import runtime_settings as runtime_state
from app.services.sheets_service import FinanceSheets

log = logging.getLogger(__name__)

sheets = FinanceSheets(config.GOOGLE_CREDENTIALS, config.SPREADSHEET_NAME, config.CURRENCY)
agent: FinanceAgent | None = None
histories: dict[int, list] = {}

STREAM_EDIT_INTERVAL = 1.5
ONB_INCOME, ONB_RED, ONB_YELLOW, ONB_GREEN = range(4)


def allowed(uid: int) -> bool:
    return not config.ALLOWED_USERS or uid in config.ALLOWED_USERS


def is_english() -> bool:
    return runtime_state.language.strip().lower().startswith("en")


def current_month() -> str:
    return datetime.datetime.now().strftime("%Y-%m")


def month_label() -> str:
    months = [
        "",
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]
    now = datetime.datetime.now()
    return f"{months[now.month]} {now.year}"


def get_agent() -> FinanceAgent:
    if agent is None:
        raise RuntimeError("Finance agent is not initialized")
    return agent


def set_agent(value: FinanceAgent) -> None:
    global agent
    agent = value


def apply_runtime_setting(key: str, value: str) -> None:
    runtime_state.update(key, value)

    if key == "currency":
        sheets.currency = value

    if agent and key in {"currency", "language", "ai_model"}:
        agent.update_preferences(
            model=runtime_state.ai_model,
            currency=runtime_state.currency,
            language=runtime_state.language,
        )
