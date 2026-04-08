"""Google Sheets integration for finance tracking — 3-zone budget system."""
from __future__ import annotations

import datetime
import uuid
from calendar import monthrange
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from app.services import sheet_styler

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ─── Категории по зонам ─────────────────────────────────────────────────────

# 🔴 Красная зона — обязательные платежи
RED_ZONE_CATEGORIES = [
    "Аренда", "Обучение", "Подписки", "Связь", "Здоровье", "Помощь семье", "Садака"
]

# 🟡 Жёлтая зона — рестораны, досуг, гулянки, питание
YELLOW_ZONE_CATEGORIES = ["Гулянки", "Питание"]

# 🟢 Зелёная зона — разовые/непредвиденные расходы
GREEN_ZONE_CATEGORIES = ["Разовые"]

INCOME_CATEGORIES = ["Зарплата", "Фриланс", "Прочее"]

# Маппинг категории → зона
CATEGORY_TO_ZONE = {c: "red" for c in RED_ZONE_CATEGORIES}
CATEGORY_TO_ZONE.update({c: "yellow" for c in YELLOW_ZONE_CATEGORIES})
CATEGORY_TO_ZONE.update({c: "green" for c in GREEN_ZONE_CATEGORIES})

SUPPORTED_SHEET_LANGUAGES = {"en", "ru"}
DEFAULT_SHEET_LANGUAGE = "en"

SHEET_TITLES = {
    "en": {
        "transactions": "Transactions",
        "budget": "Budget",
        "history": "History",
        "settings": "Settings",
        "expected_payments": "Expected Payments",
        "payment_status": "Payment Status",
    },
    "ru": {
        "transactions": "Транзакции",
        "budget": "Бюджет",
        "history": "История",
        "settings": "Настройки",
        "expected_payments": "Expected Payments",
        "payment_status": "Payment Status",
    },
}

TX_HEADERS = {
    "en": ["Date", "Type", "Amount", "Category", "Description", "Currency", "Week", "Month", "Quarter", "Half-Year", "Year", "Added At"],
    "ru": ["Дата", "Тип", "Сумма", "Категория", "Описание", "Валюта", "Неделя", "Месяц", "Квартал", "Полугодие", "Год", "Добавлено"],
}
TX_HEADER_ALIASES = {
    "date": {"Date", "Дата"},
    "type": {"Type", "Тип"},
    "amount": {"Amount", "Сумма"},
    "category": {"Category", "Категория"},
    "description": {"Description", "Описание"},
    "currency": {"Currency", "Валюта"},
    "week": {"Week", "Неделя"},
    "month": {"Month", "Месяц"},
    "quarter": {"Quarter", "Квартал"},
    "half_year": {"Half-Year", "Полугодие"},
    "year": {"Year", "Год"},
    "added_at": {"Added At", "Добавлено"},
}

HISTORY_HEADERS = {
    "en": ["Month", "Income", "Obligatory", "Fun", "One-Time", "Savings", "Total Expenses", "Balance"],
    "ru": ["Месяц", "Доходы", "Обязательное", "Гулянки", "Разовые", "Копилка", "Всего расходов", "Баланс"],
}
HISTORY_HEADER_ALIASES = {
    "month": {"Month", "Месяц"},
    "income": {"Income", "Доходы"},
    "obligatory": {"Obligatory", "Обязательное"},
    "fun": {"Fun", "Гулянки"},
    "one_time": {"One-Time", "Разовые"},
    "savings": {"Savings", "Копилка"},
    "total_expenses": {"Total Expenses", "Всего расходов"},
    "balance": {"Balance", "Баланс"},
}

SETTINGS_HEADERS = {
    "en": ["Key", "Value"],
    "ru": ["Ключ", "Значение"],
}

EXPECTED_PAYMENTS_HEADERS = [
    "id",
    "name",
    "category",
    "amount",
    "currency",
    "due_day",
    "active",
    "created_at",
    "updated_at",
]

PAYMENT_STATUS_HEADERS = [
    "payment_id",
    "month",
    "status",
    "last_reminded_at",
    "paid_at",
    "snooze_until",
    "updated_at",
]

PAYMENT_STATUS_VALUES = {"pending", "paid", "snoozed"}

TYPE_LABELS = {
    "en": {"income": "Income", "expense": "Expense", "savings": "Savings"},
    "ru": {"income": "Доход", "expense": "Расход", "savings": "Копилка"},
}
TYPE_ALIASES = {
    "income": {"Income", "Доход"},
    "expense": {"Expense", "Расход"},
    "savings": {"Savings", "Копилка"},
}

CATEGORY_LABELS = {
    "en": {
        "Аренда": "Rent",
        "Обучение": "Education",
        "Подписки": "Subscriptions",
        "Связь": "Communication",
        "Здоровье": "Health",
        "Помощь семье": "Family Support",
        "Садака": "Sadaqah",
        "Гулянки": "Fun",
        "Питание": "Food",
        "Разовые": "One-Time",
        "Зарплата": "Salary",
        "Фриланс": "Freelance",
        "Прочее": "Other",
        "Копилка": "Savings",
    },
    "ru": {},
}
CATEGORY_LABELS["ru"] = {name: name for name in CATEGORY_LABELS["en"]}
CATEGORY_ALIASES: dict[str, set[str]] = {}
for canonical_name, en_label in CATEGORY_LABELS["en"].items():
    CATEGORY_ALIASES[canonical_name] = {canonical_name, en_label}

BUDGET_TEXT = {
    "en": {
        "header": ["Category", "Limit", "Actual (auto)", "Remaining", "Zone", "Note"],
        "red_header": "🔴 RED ZONE — Obligatory",
        "yellow_header": "🟡 YELLOW ZONE — Fun, food, eating out",
        "green_header": "🟢 GREEN ZONE — One-time expenses",
        "red_total": "TOTAL 🔴",
        "yellow_total": "TOTAL 🟡",
        "green_total": "TOTAL 🟢",
        "income_block": "💰 INCOME AND PROJECTS",
        "planned_income": "Planned income",
        "project_budget": "💼 Project budget",
        "project_note": "auto: 10% of expenses",
    },
    "ru": {
        "header": ["Категория", "Лимит", "Факт (авто)", "Остаток", "Зона", "Примечание"],
        "red_header": "🔴 КРАСНАЯ ЗОНА — Обязательное",
        "yellow_header": "🟡 ЖЁЛТАЯ ЗОНА — Досуг, питание, гулянки",
        "green_header": "🟢 ЗЕЛЁНАЯ ЗОНА — Разовые расходы",
        "red_total": "ИТОГО 🔴",
        "yellow_total": "ИТОГО 🟡",
        "green_total": "ИТОГО 🟢",
        "income_block": "💰 ДОХОДЫ И ПРОЕКТЫ",
        "planned_income": "Доход (план)",
        "project_budget": "💼 Бюджет проектов",
        "project_note": "авто: 10% от расходов",
    },
}


class FinanceSheets:
    def __init__(self, credentials_file: str, spreadsheet_name: str, currency: str = "EUR"):
        self.credentials_file = credentials_file
        self.spreadsheet_name = spreadsheet_name
        self.currency = currency
        self.gc = None
        self.sh = None
        self.creds = None
        self.sheet_language = DEFAULT_SHEET_LANGUAGE

    # ─── Connection ────────────────────────────────────────────────────────────

    def connect(self):
        import os, json
        def parse_service_account_json(raw: str | None) -> dict | None:
            if not raw:
                return None

            candidate = raw.strip()
            if candidate.startswith("'") and candidate.endswith("'"):
                candidate = candidate[1:-1]

            for payload in (candidate, candidate.replace("\\n", "\n")):
                try:
                    info = json.loads(payload)
                    if isinstance(info, dict) and info.get("type") == "service_account":
                        return info
                except json.JSONDecodeError:
                    continue
            return None

        creds_json_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
        creds_file_value = self.credentials_file

        info = parse_service_account_json(creds_json_env)
        if info is None:
            info = parse_service_account_json(creds_file_value)

        if info is not None:
            self.creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            self.creds = Credentials.from_service_account_file(creds_file_value, scopes=SCOPES)
        
        self.gc = gspread.authorize(self.creds)
        try:
            self.sh = self.gc.open(self.spreadsheet_name)
        except gspread.SpreadsheetNotFound:
            self.sh = self.gc.create(self.spreadsheet_name)
            self._init_spreadsheet()
        self._ensure_sheets()
        self.sheet_language = self._get_sheet_language()

    def _init_spreadsheet(self):
        ws = self.sh.get_worksheet(0)
        ws.update_title(self._sheet_title("transactions", DEFAULT_SHEET_LANGUAGE))
        self._setup_tx_sheet(ws, DEFAULT_SHEET_LANGUAGE)
        ws2 = self.sh.add_worksheet(self._sheet_title("budget", DEFAULT_SHEET_LANGUAGE), rows=60, cols=6)
        self._setup_budget_sheet(ws2, DEFAULT_SHEET_LANGUAGE)
        ws3 = self.sh.add_worksheet(self._sheet_title("history", DEFAULT_SHEET_LANGUAGE), rows=100, cols=10)
        self._setup_history_sheet(ws3, DEFAULT_SHEET_LANGUAGE)
        ws4 = self.sh.add_worksheet(self._sheet_title("settings", DEFAULT_SHEET_LANGUAGE), rows=100, cols=2)
        self._reset_settings_sheet(ws4, DEFAULT_SHEET_LANGUAGE)
        ws5 = self.sh.add_worksheet(self._sheet_title("expected_payments", DEFAULT_SHEET_LANGUAGE), rows=200, cols=9)
        self._setup_expected_payments_sheet(ws5)
        ws6 = self.sh.add_worksheet(self._sheet_title("payment_status", DEFAULT_SHEET_LANGUAGE), rows=400, cols=7)
        self._setup_payment_status_sheet(ws6)

    def _ensure_sheets(self):
        for sheet_key, rows, cols, setup in (
            ("transactions", 2000, 12, self._setup_tx_sheet),
            ("budget", 60, 6, self._setup_budget_sheet),
            ("history", 100, 10, self._setup_history_sheet),
            ("settings", 100, 2, self._reset_settings_sheet),
            ("expected_payments", 200, 9, self._setup_expected_payments_sheet),
            ("payment_status", 400, 7, self._setup_payment_status_sheet),
        ):
            if not self._find_worksheet(sheet_key):
                ws = self.sh.add_worksheet(self._sheet_title(sheet_key, self.sheet_language), rows=rows, cols=cols)
                try:
                    setup(ws, self.sheet_language)
                except TypeError:
                    setup(ws)

    def _get_settings_ws(self):
        return self._worksheet("settings")

    def _get_expected_payments_ws(self):
        return self._worksheet("expected_payments")

    def _get_payment_status_ws(self):
        return self._worksheet("payment_status")

    def _sheet_title(self, key: str, language: str | None = None) -> str:
        lang = self._normalize_sheet_language(language)
        return SHEET_TITLES[lang][key]

    def _normalize_sheet_language(self, language: str | None) -> str:
        normalized = (language or self.sheet_language or DEFAULT_SHEET_LANGUAGE).strip().lower()
        if normalized.startswith("ru"):
            return "ru"
        return "en"

    def _find_worksheet(self, key: str):
        aliases = {titles[key] for titles in SHEET_TITLES.values()}
        for ws in self.sh.worksheets():
            if ws.title in aliases:
                return ws
        return None

    def _worksheet(self, key: str):
        ws = self._find_worksheet(key)
        if ws is None:
            raise gspread.WorksheetNotFound(key)
        return ws

    def _display_type(self, canonical_type: str, language: str | None = None) -> str:
        lang = self._normalize_sheet_language(language)
        return TYPE_LABELS[lang][canonical_type]

    def _canonical_type(self, value: str) -> str:
        raw = str(value or "").strip()
        for canonical, aliases in TYPE_ALIASES.items():
            if raw in aliases:
                return canonical
        return raw.lower() or "expense"

    def _display_category(self, canonical_category: str, language: str | None = None) -> str:
        lang = self._normalize_sheet_language(language)
        return CATEGORY_LABELS[lang].get(canonical_category, canonical_category)

    def _canonical_category(self, value: str) -> str:
        raw = str(value or "").strip()
        for canonical, aliases in CATEGORY_ALIASES.items():
            if raw in aliases:
                return canonical
        return raw

    def _record_value(self, record: dict, aliases: dict[str, set[str]], key: str, default=""):
        for alias in aliases[key]:
            if alias in record:
                return record.get(alias, default)
        return default

    def _normalize_tx_record(self, record: dict) -> dict:
        normalized: dict[str, str] = {}
        for key in TX_HEADER_ALIASES:
            normalized[key] = self._record_value(record, TX_HEADER_ALIASES, key, "")
        normalized["type"] = self._canonical_type(normalized["type"])
        normalized["category"] = self._canonical_category(normalized["category"])
        return normalized

    def _normalize_history_record(self, record: dict) -> dict:
        normalized: dict[str, str] = {}
        for key in HISTORY_HEADER_ALIASES:
            normalized[key] = self._record_value(record, HISTORY_HEADER_ALIASES, key, 0 if key != "month" else "")
        return normalized

    def _get_sheet_language(self) -> str:
        try:
            settings_ws = self._get_settings_ws()
            rows = settings_ws.get_all_values()
            for row in rows[1:]:
                if len(row) >= 2 and str(row[0]).strip() == "sheet_language":
                    return self._normalize_sheet_language(row[1])
                if len(row) >= 2 and str(row[0]).strip() == "language":
                    return self._normalize_sheet_language(row[1])
        except Exception:
            pass
        try:
            tx_ws = self._worksheet("transactions")
            header = str(tx_ws.acell("A1").value or "").strip()
            if header == "Дата":
                return "ru"
        except Exception:
            pass
        return DEFAULT_SHEET_LANGUAGE

    def _reset_settings_sheet(self, ws, language: str | None = None) -> None:
        headers = SETTINGS_HEADERS[self._normalize_sheet_language(language)]
        ws.clear()
        ws.update("A1:B1", [headers])
        ws.freeze(rows=1)

    def _setup_expected_payments_sheet(self, ws) -> None:
        try:
            if ws.acell("A1").value == EXPECTED_PAYMENTS_HEADERS[0]:
                return
        except Exception:
            pass
        ws.clear()
        ws.update("A1:I1", [EXPECTED_PAYMENTS_HEADERS])
        ws.freeze(rows=1)

    def _setup_payment_status_sheet(self, ws) -> None:
        try:
            if ws.acell("A1").value == PAYMENT_STATUS_HEADERS[0]:
                return
        except Exception:
            pass
        ws.clear()
        ws.update("A1:G1", [PAYMENT_STATUS_HEADERS])
        ws.freeze(rows=1)

    def _now_iso(self) -> str:
        return datetime.datetime.now().replace(microsecond=0).isoformat()

    def current_month_key(self, today: datetime.date | None = None) -> str:
        base = today or datetime.date.today()
        return base.strftime("%Y-%m")

    def get_due_date(self, due_day: int, month: str | None = None) -> datetime.date:
        if month:
            year, mon = month.split("-", 1)
            base_year = int(year)
            base_month = int(mon)
        else:
            today = datetime.date.today()
            base_year = today.year
            base_month = today.month
        safe_day = max(1, min(int(due_day), monthrange(base_year, base_month)[1]))
        return datetime.date(base_year, base_month, safe_day)

    def is_expected_payment_due(self, due_day: int, today: datetime.date | None = None) -> bool:
        due_date = self.get_due_date(due_day, self.current_month_key(today))
        base = today or datetime.date.today()
        delta = (due_date - base).days
        return delta in {7, 3, 1, 0} or delta < 0

    def due_timing_label(self, due_day: int, today: datetime.date | None = None) -> str:
        due_date = self.get_due_date(due_day, self.current_month_key(today))
        base = today or datetime.date.today()
        delta = (due_date - base).days
        if delta > 1:
            return f"due in {delta} days"
        if delta == 1:
            return "due tomorrow"
        if delta == 0:
            return "due today"
        if delta == -1:
            return "overdue by 1 day"
        return f"overdue by {abs(delta)} days"

    def _payment_from_row(self, row: list[str]) -> dict:
        padded = (row + [""] * len(EXPECTED_PAYMENTS_HEADERS))[: len(EXPECTED_PAYMENTS_HEADERS)]
        return {
            "id": str(padded[0]).strip(),
            "name": str(padded[1]).strip(),
            "category": self._canonical_category(padded[2]),
            "amount": self._safe_float(padded[3]),
            "currency": str(padded[4]).strip() or self.currency,
            "due_day": int(self._safe_float(padded[5]) or 0),
            "active": str(padded[6]).strip().lower() in {"true", "1", "yes"},
            "created_at": str(padded[7]).strip(),
            "updated_at": str(padded[8]).strip(),
        }

    def _status_from_row(self, row: list[str]) -> dict:
        padded = (row + [""] * len(PAYMENT_STATUS_HEADERS))[: len(PAYMENT_STATUS_HEADERS)]
        status = str(padded[2]).strip().lower() or "pending"
        if status not in PAYMENT_STATUS_VALUES:
            status = "pending"
        return {
            "payment_id": str(padded[0]).strip(),
            "month": str(padded[1]).strip(),
            "status": status,
            "last_reminded_at": str(padded[3]).strip(),
            "paid_at": str(padded[4]).strip(),
            "snooze_until": str(padded[5]).strip(),
            "updated_at": str(padded[6]).strip(),
        }

    def _safe_float(self, value) -> float:
        try:
            if value is None:
                return 0.0
            return float(str(value).replace(" ", "").replace(",", ".") or 0)
        except Exception:
            return 0.0

    def get_setting(self, key: str, default: str = "") -> str:
        ws = self._get_settings_ws()
        rows = ws.get_all_values()
        for row in rows[1:]:
            if len(row) >= 2 and str(row[0]).strip() == key:
                return str(row[1]).strip()
        return default

    def set_setting(self, key: str, value: str) -> dict:
        ws = self._get_settings_ws()
        rows = ws.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            if len(row) >= 1 and str(row[0]).strip() == key:
                ws.update(f"B{i}", [[str(value)]])
                return {"success": True, "key": key, "value": value}
        ws.append_row([key, str(value)], value_input_option="USER_ENTERED")
        return {"success": True, "key": key, "value": value}

    def list_expected_payments(self, active_only: bool = False) -> list[dict]:
        ws = self._get_expected_payments_ws()
        rows = ws.get_all_values()[1:]
        payments = [self._payment_from_row(row) for row in rows if row and any(str(cell).strip() for cell in row)]
        payments = [payment for payment in payments if payment["id"]]
        if active_only:
            payments = [payment for payment in payments if payment["active"]]
        payments.sort(key=lambda payment: (not payment["active"], payment["due_day"], payment["name"].lower()))
        return payments

    def get_expected_payment(self, payment_id: str) -> dict | None:
        for payment in self.list_expected_payments(active_only=False):
            if payment["id"] == payment_id:
                return payment
        return None

    def create_expected_payment(self, name: str, category: str, amount: float, due_day: int, currency: str | None = None) -> dict:
        ws = self._get_expected_payments_ws()
        now_iso = self._now_iso()
        payment = {
            "id": uuid.uuid4().hex[:12],
            "name": str(name).strip(),
            "category": self._canonical_category(category),
            "amount": round(float(amount), 2),
            "currency": str(currency or self.currency).strip() or self.currency,
            "due_day": max(1, min(int(due_day), 31)),
            "active": True,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        ws.append_row(
            [
                payment["id"],
                payment["name"],
                self._display_category(payment["category"], "en"),
                payment["amount"],
                payment["currency"],
                payment["due_day"],
                "TRUE",
                payment["created_at"],
                payment["updated_at"],
            ],
            value_input_option="USER_ENTERED",
        )
        return payment

    def update_expected_payment(self, payment_id: str, **fields) -> dict | None:
        ws = self._get_expected_payments_ws()
        rows = ws.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            payment = self._payment_from_row(row)
            if payment["id"] != payment_id:
                continue

            payment["name"] = str(fields.get("name", payment["name"])).strip()
            if "category" in fields:
                payment["category"] = self._canonical_category(fields["category"])
            if "amount" in fields:
                payment["amount"] = round(float(fields["amount"]), 2)
            if "currency" in fields:
                payment["currency"] = str(fields["currency"]).strip() or payment["currency"]
            if "due_day" in fields:
                payment["due_day"] = max(1, min(int(fields["due_day"]), 31))
            if "active" in fields:
                payment["active"] = bool(fields["active"])
            payment["updated_at"] = self._now_iso()

            ws.update(
                f"A{i}:I{i}",
                [[
                    payment["id"],
                    payment["name"],
                    self._display_category(payment["category"], "en"),
                    payment["amount"],
                    payment["currency"],
                    payment["due_day"],
                    "TRUE" if payment["active"] else "FALSE",
                    payment["created_at"],
                    payment["updated_at"],
                ]],
            )
            return payment
        return None

    def delete_expected_payment(self, payment_id: str) -> bool:
        ws = self._get_expected_payments_ws()
        rows = ws.get_all_values()
        deleted = False
        for i, row in enumerate(rows[1:], start=2):
            payment = self._payment_from_row(row)
            if payment["id"] == payment_id:
                ws.delete_rows(i)
                deleted = True
                break
        if deleted:
            status_ws = self._get_payment_status_ws()
            status_rows = status_ws.get_all_values()
            for i in range(len(status_rows) - 1, 0, -1):
                row = status_rows[i]
                if row and str(row[0]).strip() == payment_id:
                    status_ws.delete_rows(i + 1)
        return deleted

    def get_payment_status(self, payment_id: str, month: str) -> dict:
        ws = self._get_payment_status_ws()
        rows = ws.get_all_values()[1:]
        for row in rows:
            status = self._status_from_row(row)
            if status["payment_id"] == payment_id and status["month"] == month:
                return status
        return {
            "payment_id": payment_id,
            "month": month,
            "status": "pending",
            "last_reminded_at": "",
            "paid_at": "",
            "snooze_until": "",
            "updated_at": "",
        }

    def upsert_payment_status(
        self,
        payment_id: str,
        month: str,
        *,
        status: str | None = None,
        last_reminded_at: str | None = None,
        paid_at: str | None = None,
        snooze_until: str | None = None,
    ) -> dict:
        ws = self._get_payment_status_ws()
        rows = ws.get_all_values()
        now_iso = self._now_iso()
        updated_status = None

        for i, row in enumerate(rows[1:], start=2):
            current = self._status_from_row(row)
            if current["payment_id"] != payment_id or current["month"] != month:
                continue
            if status is not None:
                current["status"] = status if status in PAYMENT_STATUS_VALUES else "pending"
            if last_reminded_at is not None:
                current["last_reminded_at"] = last_reminded_at
            if paid_at is not None:
                current["paid_at"] = paid_at
            if snooze_until is not None:
                current["snooze_until"] = snooze_until
            current["updated_at"] = now_iso
            ws.update(
                f"A{i}:G{i}",
                [[
                    current["payment_id"],
                    current["month"],
                    current["status"],
                    current["last_reminded_at"],
                    current["paid_at"],
                    current["snooze_until"],
                    current["updated_at"],
                ]],
            )
            updated_status = current
            break

        if updated_status is None:
            updated_status = {
                "payment_id": payment_id,
                "month": month,
                "status": status if status in PAYMENT_STATUS_VALUES else "pending",
                "last_reminded_at": last_reminded_at or "",
                "paid_at": paid_at or "",
                "snooze_until": snooze_until or "",
                "updated_at": now_iso,
            }
            ws.append_row(
                [
                    updated_status["payment_id"],
                    updated_status["month"],
                    updated_status["status"],
                    updated_status["last_reminded_at"],
                    updated_status["paid_at"],
                    updated_status["snooze_until"],
                    updated_status["updated_at"],
                ],
                value_input_option="USER_ENTERED",
            )

        return updated_status

    def mark_payment_paid(self, payment_id: str, month: str) -> dict:
        return self.upsert_payment_status(
            payment_id,
            month,
            status="paid",
            paid_at=self._now_iso(),
            snooze_until="",
        )

    def snooze_payment(self, payment_id: str, month: str, days: int = 1) -> dict:
        snooze_date = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
        return self.upsert_payment_status(payment_id, month, status="snoozed", snooze_until=snooze_date)

    def record_payment_reminder(self, payment_id: str, month: str) -> dict:
        return self.upsert_payment_status(
            payment_id,
            month,
            status="pending",
            last_reminded_at=datetime.date.today().isoformat(),
        )

    def localize_spreadsheet(self, language: str) -> None:
        language = self._normalize_sheet_language(language)
        if not self.sh:
            raise RuntimeError("Spreadsheet is not connected")

        tx_ws = self._worksheet("transactions")
        budget_ws = self._worksheet("budget")
        history_ws = self._worksheet("history")
        settings_ws = self._worksheet("settings")
        payments_ws = self._worksheet("expected_payments")
        payment_status_ws = self._worksheet("payment_status")

        self._localize_transactions_sheet(tx_ws, language)
        self._localize_budget_sheet(budget_ws, language)
        self._localize_history_sheet(history_ws, language)
        self._localize_settings_sheet(settings_ws, language)

        tx_ws.update_title(self._sheet_title("transactions", language))
        budget_ws.update_title(self._sheet_title("budget", language))
        history_ws.update_title(self._sheet_title("history", language))
        settings_ws.update_title(self._sheet_title("settings", language))

        self.sheet_language = language
        self.set_setting("sheet_language", language)

    def _localize_transactions_sheet(self, ws, language: str) -> None:
        rows = ws.get_all_values()
        if len(rows) <= 1:
            self._setup_tx_sheet(ws, language)
            return
        localized_rows = [TX_HEADERS[language]]
        for row in rows[1:]:
            padded = row + [""] * (12 - len(row))
            padded = padded[:12]
            padded[1] = self._display_type(self._canonical_type(padded[1]), language)
            padded[3] = self._display_category(self._canonical_category(padded[3]), language)
            localized_rows.append(padded)
        ws.clear()
        ws.update(f"A1:L{len(localized_rows)}", localized_rows)
        self._setup_tx_sheet(ws, language)

    def _localize_budget_sheet(self, ws, language: str) -> None:
        plan_month = ""
        project_accumulated = 0.0
        plan = {}
        try:
            cell = (ws.acell("F1").value or "").replace("📅", "").strip()
            if len(cell) == 7 and cell[4] == "-":
                plan_month = cell
        except Exception:
            pass
        if plan_month:
            try:
                plan = self.get_budget_plan(plan_month)
            except Exception:
                plan = {}
            try:
                project_accumulated = float(ws.acell(f"C{self._get_project_budget_row()}").value or 0)
            except Exception:
                project_accumulated = 0.0

        ws.clear()
        self._setup_budget_sheet(ws, language)
        if plan_month and plan:
            self.set_budget_plan(
                month=plan_month,
                income=plan.get("income", 0),
                red_limits=plan.get("red", {}),
                yellow_limit=plan.get("yellow", 0),
                green_limit=plan.get("green", 0),
            )
            ws.update(f"C{self._get_project_budget_row()}", [[project_accumulated]])
            self.update_budget_fact(plan_month)

    def _localize_history_sheet(self, ws, language: str) -> None:
        records = [self._normalize_history_record(record) for record in ws.get_all_records()]
        ws.clear()
        self._setup_history_sheet(ws, language)
        if not records:
            return
        rows = [
            [
                record["month"],
                record["income"],
                record["obligatory"],
                record["fun"],
                record["one_time"],
                record["savings"],
                record["total_expenses"],
                record["balance"],
            ]
            for record in records
        ]
        ws.update(f"A2:H{len(rows) + 1}", rows)

    def _localize_settings_sheet(self, ws, language: str) -> None:
        rows = ws.get_all_values()[1:]
        self._reset_settings_sheet(ws, language)
        for row in rows:
            if row:
                ws.append_row((row + [""])[:2], value_input_option="USER_ENTERED")

    def reset_all_data(self) -> dict:
        if not self.sh:
            raise RuntimeError("Spreadsheet is not connected")

        tx_ws = self._worksheet("transactions")
        budget_ws = self._worksheet("budget")
        history_ws = self._worksheet("history")
        settings_ws = self._worksheet("settings")

        tx_ws.clear()
        self._setup_tx_sheet(tx_ws, DEFAULT_SHEET_LANGUAGE)

        budget_ws.clear()
        self._setup_budget_sheet(budget_ws, DEFAULT_SHEET_LANGUAGE)

        history_ws.clear()
        self._setup_history_sheet(history_ws, DEFAULT_SHEET_LANGUAGE)

        self._reset_settings_sheet(settings_ws, DEFAULT_SHEET_LANGUAGE)
        payments_ws.clear()
        self._setup_expected_payments_sheet(payments_ws)
        payment_status_ws.clear()
        self._setup_payment_status_sheet(payment_status_ws)
        tx_ws.update_title(self._sheet_title("transactions", DEFAULT_SHEET_LANGUAGE))
        budget_ws.update_title(self._sheet_title("budget", DEFAULT_SHEET_LANGUAGE))
        history_ws.update_title(self._sheet_title("history", DEFAULT_SHEET_LANGUAGE))
        settings_ws.update_title(self._sheet_title("settings", DEFAULT_SHEET_LANGUAGE))
        payments_ws.update_title(self._sheet_title("expected_payments", DEFAULT_SHEET_LANGUAGE))
        payment_status_ws.update_title(self._sheet_title("payment_status", DEFAULT_SHEET_LANGUAGE))
        self.sheet_language = DEFAULT_SHEET_LANGUAGE

        return {"success": True, "spreadsheet_url": self.get_spreadsheet_url()}

    # ─── Sheet Setup ───────────────────────────────────────────────────────────

    def _setup_tx_sheet(self, ws, language: str | None = None):
        headers = TX_HEADERS[self._normalize_sheet_language(language)]
        try:
            if ws.acell("A1").value == headers[0]:
                return
        except Exception:
            pass
        ws.update("A1:L1", [headers])
        ws.format("A1:L1", {
            "backgroundColor": {"red": 0.13, "green": 0.59, "blue": 0.95},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })
        sheet_styler.apply_tx_styling(self.sh, ws)

    def _get_row_layout(self) -> dict:
        """Вычисляет все номера строк листа Бюджет динамически на основе списков категорий."""
        r = {}
        # Row 1: headers/title
        # Row 2: red zone header
        r["red_header"] = 2
        r["red_start"] = 3
        r["red_end"] = 3 + len(RED_ZONE_CATEGORIES) - 1
        r["red_itogo"] = r["red_end"] + 1

        r["yellow_header"] = r["red_itogo"] + 2
        r["yellow_start"] = r["yellow_header"] + 1
        r["yellow_end"] = r["yellow_start"] + len(YELLOW_ZONE_CATEGORIES) - 1
        r["yellow_itogo"] = r["yellow_end"] + 1

        r["green_header"] = r["yellow_itogo"] + 2
        r["green_start"] = r["green_header"] + 1
        r["green_end"] = r["green_start"] + len(GREEN_ZONE_CATEGORIES) - 1
        r["green_itogo"] = r["green_end"] + 1

        r["inc_header"] = r["green_itogo"] + 2
        r["inc_row"] = r["inc_header"] + 1
        r["proj_row"] = r["inc_row"] + 1
        return r

    def _setup_budget_sheet(self, ws, language: str | None = None):
        """Три цветных блока бюджета + доходы/проекты."""
        lang = self._normalize_sheet_language(language)
        text = BUDGET_TEXT[lang]
        L = self._get_row_layout()
        ws.freeze(rows=1)
        # Title row
        ws.update("A1:F1", [text["header"]])
        ws.format("A1:F1", {
            "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })

        # 🔴 Red zone
        r_h = L["red_header"]
        ws.update(f"A{r_h}:F{r_h}", [[text["red_header"], "", "", "", "", ""]])
        ws.format(f"A{r_h}:F{r_h}", {
            "backgroundColor": {"red": 0.95, "green": 0.8, "blue": 0.8},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.6, "green": 0.1, "blue": 0.1}},
        })
        for i, cat in enumerate(RED_ZONE_CATEGORIES):
            row = L["red_start"] + i
            ws.update(f"A{row}:F{row}", [[self._display_category(cat, lang), 0, 0, f"=B{row}-C{row}", "red", ""]])
        ws.format(f"A{L['red_start']}:F{L['red_end']}", {
            "backgroundColor": {"red": 1.0, "green": 0.93, "blue": 0.93},
        })
        r_it = L["red_itogo"]
        ws.update(f"A{r_it}:F{r_it}", [[text["red_total"],
            f"=SUM(B{L['red_start']}:B{L['red_end']})",
            f"=SUM(C{L['red_start']}:C{L['red_end']})",
            f"=B{r_it}-C{r_it}", "", ""]])
        ws.format(f"A{r_it}:F{r_it}", {"textFormat": {"bold": True}})

        # 🟡 Yellow zone
        y_h = L["yellow_header"]
        ws.update(f"A{y_h}:F{y_h}", [[text["yellow_header"], "", "", "", "", ""]])
        ws.format(f"A{y_h}:F{y_h}", {
            "backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.7},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.5, "green": 0.35, "blue": 0.0}},
        })
        for i, cat in enumerate(YELLOW_ZONE_CATEGORIES):
            row = L["yellow_start"] + i
            ws.update(f"A{row}:F{row}", [[self._display_category(cat, lang), 0, 0, f"=B{row}-C{row}", "yellow", ""]])
        ws.format(f"A{L['yellow_start']}:F{L['yellow_end']}", {
            "backgroundColor": {"red": 1.0, "green": 0.98, "blue": 0.85},
        })
        y_it = L["yellow_itogo"]
        ws.update(f"A{y_it}:F{y_it}", [[text["yellow_total"],
            f"=SUM(B{L['yellow_start']}:B{L['yellow_end']})",
            f"=SUM(C{L['yellow_start']}:C{L['yellow_end']})",
            f"=B{y_it}-C{y_it}", "", ""]])
        ws.format(f"A{y_it}:F{y_it}", {"textFormat": {"bold": True}})

        # 🟢 Green zone
        g_h = L["green_header"]
        ws.update(f"A{g_h}:F{g_h}", [[text["green_header"], "", "", "", "", ""]])
        ws.format(f"A{g_h}:F{g_h}", {
            "backgroundColor": {"red": 0.8, "green": 0.95, "blue": 0.8},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.1, "green": 0.45, "blue": 0.1}},
        })
        for i, cat in enumerate(GREEN_ZONE_CATEGORIES):
            row = L["green_start"] + i
            ws.update(f"A{row}:F{row}", [[self._display_category(cat, lang), 0, 0, f"=B{row}-C{row}", "green", ""]])
        ws.format(f"A{L['green_start']}:F{L['green_end']}", {
            "backgroundColor": {"red": 0.92, "green": 1.0, "blue": 0.92},
        })
        g_it = L["green_itogo"]
        ws.update(f"A{g_it}:F{g_it}", [[text["green_total"],
            f"=SUM(B{L['green_start']}:B{L['green_end']})",
            f"=SUM(C{L['green_start']}:C{L['green_end']})",
            f"=B{g_it}-C{g_it}", "", ""]])
        ws.format(f"A{g_it}:F{g_it}", {"textFormat": {"bold": True}})

        # 💰 Income + Projects block
        i_h = L["inc_header"]
        ws.update(f"A{i_h}:F{i_h}", [[text["income_block"], "", "", "", "", ""]])
        ws.format(f"A{i_h}:F{i_h}", {
            "backgroundColor": {"red": 0.8, "green": 0.85, "blue": 0.95},
            "textFormat": {"bold": True},
        })
        i_r = L["inc_row"]
        ws.update(f"A{i_r}:F{i_r}", [[text["planned_income"], 0, 0, "", "", ""]])
        p_r = L["proj_row"]
        ws.update(f"A{p_r}:F{p_r}", [[text["project_budget"], 0, 0, "", "", text["project_note"]]])
        ws.format(f"A{p_r}:F{p_r}", {
            "backgroundColor": {"red": 0.85, "green": 0.78, "blue": 0.95},
            "textFormat": {"bold": True},
        })

    def _setup_history_sheet(self, ws, language: str | None = None):
        headers = HISTORY_HEADERS[self._normalize_sheet_language(language)]
        try:
            if ws.acell("A1").value == headers[0]:
                return
        except Exception:
            pass
        ws.update("A1:H1", [headers])
        ws.format("A1:H1", {
            "backgroundColor": {"red": 0.2, "green": 0.7, "blue": 0.3},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })
        ws.freeze(rows=1)

    # ─── Budget Plan Management ─────────────────────────────────────────────────

    def _get_budget_ws(self):
        return self._worksheet("budget")

    def set_budget_plan(self, month: str, income: float,
                        red_limits: dict, yellow_limit: float, green_limit: float) -> dict:
        ws = self._get_budget_ws()
        L = self._get_row_layout()
        ws.update("F1", [[f"📅 {month}"]])

        for i, cat in enumerate(RED_ZONE_CATEGORIES):
            ws.update(f"B{L['red_start'] + i}", [[red_limits.get(cat, 0)]])

        # Yellow: distribute yellow_limit equally across yellow categories
        per_yellow = round(yellow_limit / len(YELLOW_ZONE_CATEGORIES), 2) if YELLOW_ZONE_CATEGORIES else 0
        for i in range(len(YELLOW_ZONE_CATEGORIES)):
            ws.update(f"B{L['yellow_start'] + i}", [[per_yellow]])

        # Green
        ws.update(f"B{L['green_start']}", [[green_limit]])

        # Income
        ws.update(f"B{L['inc_row']}", [[income]])

        # Reset project budget for new month
        ws.update(f"B{L['proj_row']}", [[0]])
        ws.update(f"C{L['proj_row']}", [[0]])

        return {"success": True, "month": month}

    def get_budget_plan(self, month: str) -> dict:
        """Return the current plan stored in the budget sheet."""
        ws = self._get_budget_ws()
        # Check if this month
        cell = ws.acell("F1").value or ""
        if month not in cell:
            return {}  # No plan for this month yet

        all_vals = ws.get_all_values()
        L = self._get_row_layout()

        def _safe_float(value) -> float:
            try:
                if value is None:
                    return 0.0
                return float(str(value).replace(" ", "").replace(",", ".") or 0)
            except Exception:
                return 0.0

        result = {"month": month, "red": {}, "yellow": 0, "green": 0, "income": 0}

        def _b_col(row: int) -> float:
            idx = row - 1
            if idx < 0 or idx >= len(all_vals):
                return 0.0
            row_vals = all_vals[idx]
            if len(row_vals) < 2:
                return 0.0
            return _safe_float(row_vals[1])

        for i, cat in enumerate(RED_ZONE_CATEGORIES):
            row_idx = L["red_start"] + i
            result["red"][cat] = _b_col(row_idx)

        # yellow/green/income are read from dynamic layout
        result["yellow"] = _b_col(L["yellow_start"])
        result["green"] = _b_col(L["green_start"])
        result["income"] = _b_col(L["inc_row"])
        return result

    def has_budget_for_month(self, month: str) -> bool:
        """Check whether a budget plan exists for this month."""
        ws = self._get_budget_ws()
        cell = ws.acell("F1").value or ""
        return month in cell

    def _get_project_budget_row(self) -> int:
        return self._get_row_layout()["proj_row"]

    def _add_to_project_budget(self, amount: float):
        if not self.has_budget_for_month(datetime.datetime.now().strftime("%Y-%m")):
            return
        ws = self._get_budget_ws()
        proj_row = self._get_project_budget_row()
        try:
            current = float(ws.acell(f"C{proj_row}").value or 0)
            ws.update(f"C{proj_row}", [[round(current + amount, 2)]])
        except Exception:
            pass

    def get_project_budget(self) -> dict:
        ws = self._get_budget_ws()
        proj_row = self._get_project_budget_row()
        try:
            accumulated = float(ws.acell(f"C{proj_row}").value or 0)
            return {"accumulated": accumulated, "currency": self.currency}
        except Exception:
            return {"accumulated": 0, "currency": self.currency}

    def update_budget_fact(self, month: str):
        """Recalculate fact column in budget sheet from transactions."""
        if not self.has_budget_for_month(month):
            return
        ws_tx = self._worksheet("transactions")
        all_tx = [self._normalize_tx_record(r) for r in ws_tx.get_all_records()]
        month_tx = [r for r in all_tx if r.get("month") == month]

        def _sum(cat_list, tx_type="expense"):
            return sum(
                float(str(r.get("amount", 0)).replace(",", "."))
                for r in month_tx if r.get("type") == tx_type and r.get("category") in cat_list
            )

        ws_b = self._get_budget_ws()
        L = self._get_row_layout()

        # Red zone: update each category row
        for i, cat in enumerate(RED_ZONE_CATEGORIES):
            row = L["red_start"] + i
            ws_b.update(f"C{row}", [[round(_sum([cat]), 2)]])

        # Yellow zone: update each category row separately
        for i, cat in enumerate(YELLOW_ZONE_CATEGORIES):
            row = L["yellow_start"] + i
            ws_b.update(f"C{row}", [[round(_sum([cat]), 2)]])

        # Green zone
        for i, cat in enumerate(GREEN_ZONE_CATEGORIES):
            row = L["green_start"] + i
            ws_b.update(f"C{row}", [[round(_sum([cat]), 2)]])

        # Income fact
        income_fact = _sum(INCOME_CATEGORIES, "income")
        ws_b.update(f"C{L['inc_row']}", [[round(income_fact, 2)]])

    # ─── Write transactions ─────────────────────────────────────────────────────

    def add_transaction(self, amount: float, category: str, description: str,
                        trans_type: str, trans_date: Optional[str] = None) -> dict:
        ws = self._worksheet("transactions")
        now = datetime.datetime.now()

        if trans_date is None:
            trans_date = now.strftime("%d.%m.%Y")

        try:
            dt = datetime.datetime.strptime(trans_date, "%d.%m.%Y")
        except ValueError:
            dt = now

        isocal = dt.isocalendar()
        week_str = f"{dt.year}-W{isocal[1]:02d}"
        month_str = dt.strftime("%Y-%m")
        quarter_str = f"{dt.year}-Q{(dt.month-1)//3 + 1}"
        half_str = f"{dt.year}-H1" if dt.month <= 6 else f"{dt.year}-H2"

        row = [
            trans_date,
            self._display_type(self._canonical_type(trans_type), self.sheet_language),
            round(float(amount), 2),
            self._display_category(self._canonical_category(category), self.sheet_language),
            description,
            self.currency, week_str, month_str, quarter_str, half_str, str(dt.year),
            now.strftime("%d.%m.%Y %H:%M"),
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

        # Auto-allocate 10% of every expense to project budget
        contribution = 0.0
        if self._canonical_type(trans_type) == "expense":
            contribution = round(float(amount) * 0.10, 2)
            self._add_to_project_budget(contribution)

        result = {
            "success": True,
            "date": trans_date,
            "type": self._canonical_type(trans_type),
            "amount": round(float(amount), 2),
            "category": self._canonical_category(category),
            "description": description,
            "zone": CATEGORY_TO_ZONE.get(category, "unknown"),
            "affected_month": month_str,  # caller should sync budget fact once
        }
        if contribution > 0:
            result["project_budget_contribution"] = contribution
        return result

    # ─── Search / Edit / Delete ─────────────────────────────────────────────────

    def search_transactions(self, query: str = "", limit: int = 10) -> list[dict]:
        ws = self._worksheet("transactions")
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return []

        results = []
        for idx in range(len(all_values) - 1, 0, -1):
            row = all_values[idx]
            row_dict = {
                "row_id": idx + 1,
                "date": row[0], "type": row[1], "amount": row[2],
                "category": row[3], "description": row[4],
            }
            if not query or query.lower() in " ".join(row).lower():
                results.append(row_dict)
                if len(results) >= limit:
                    break
        return results

    def delete_last_transaction(self) -> dict:
        ws = self._worksheet("transactions")
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return {"success": False, "message": "Нет транзакций для удаления"}
        last_row = len(all_values)
        deleted = all_values[last_row - 1]
        ws.delete_rows(last_row)
        month_str = deleted[7] if len(deleted) > 7 else datetime.datetime.now().strftime("%Y-%m")
        self._sync_history(month_str)
        self.update_budget_fact(month_str)
        return {"success": True, "deleted": {"date": deleted[0], "type": deleted[1],
                                              "amount": deleted[2], "category": deleted[3]}}

    def delete_transaction(self, row_id: int) -> dict:
        ws = self._worksheet("transactions")
        all_values = ws.get_all_values()
        if row_id <= 1 or row_id > len(all_values):
            return {"success": False, "message": "Некорректный ID строки"}
        deleted = all_values[row_id - 1]
        ws.delete_rows(row_id)
        month_str = deleted[7] if len(deleted) > 7 else datetime.datetime.now().strftime("%Y-%m")
        self._sync_history(month_str)
        self.update_budget_fact(month_str)
        return {"success": True, "deleted": {"date": deleted[0], "type": deleted[1],
                                              "amount": deleted[2], "category": deleted[3]}}

    def edit_transaction(self, row_id: int, amount: float = None, category: str = None,
                         description: str = None, trans_date: str = None) -> dict:
        ws = self._worksheet("transactions")
        all_values = ws.get_all_values()
        if row_id <= 1 or row_id > len(all_values):
            return {"success": False, "message": "Некорректный ID строки"}
        row = all_values[row_id - 1]
        if trans_date is not None:
            row[0] = trans_date
        if amount is not None:
            row[2] = str(round(float(amount), 2))
        if category is not None:
            row[3] = self._display_category(self._canonical_category(category), self.sheet_language)
        if description is not None:
            row[4] = description

        try:
            dt = datetime.datetime.strptime(row[0], "%d.%m.%Y")
        except ValueError:
            dt = datetime.datetime.now()

        isocal = dt.isocalendar()
        row[6] = f"{dt.year}-W{isocal[1]:02d}"
        row[7] = dt.strftime("%Y-%m")
        row[8] = f"{dt.year}-Q{(dt.month - 1)//3 + 1}"
        row[9] = f"{dt.year}-H1" if dt.month <= 6 else f"{dt.year}-H2"
        row[10] = str(dt.year)
        if len(row) < 12:
            row.extend([""] * (12 - len(row)))
        row[11] = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

        if len(row) > 1:
            row[1] = self._display_type(self._canonical_type(row[1]), self.sheet_language)
        ws.update(f"A{row_id}:L{row_id}", [row[:12]])
        month_str = row[7] if len(row) > 7 else datetime.datetime.now().strftime("%Y-%m")
        self._sync_history(month_str)
        self.update_budget_fact(month_str)
        return {"success": True, "message": "Успешно изменено"}

    # ─── Aggregations ───────────────────────────────────────────────────────────

    def _sync_history(self, month: str):
        records = [self._normalize_tx_record(r) for r in self._worksheet("transactions").get_all_records()]
        month_records = [r for r in records if r.get("month") == month]

        def _s(cat_filter=None, type_filter=None):
            return sum(
                float(str(r.get("amount", 0)).replace(",", "."))
                for r in month_records
                if (type_filter is None or r.get("type") == type_filter)
                and (cat_filter is None or r.get("category") in cat_filter)
            )

        income = _s(type_filter="income")
        obligatory = _s(cat_filter=RED_ZONE_CATEGORIES, type_filter="expense")
        fun = _s(cat_filter=YELLOW_ZONE_CATEGORIES, type_filter="expense")
        one_time = _s(cat_filter=GREEN_ZONE_CATEGORIES, type_filter="expense")
        savings = _s(type_filter="savings")
        total_exp = obligatory + fun + one_time + savings
        balance = income - total_exp

        ws_hist = self._worksheet("history")
        hist_records = [self._normalize_history_record(r) for r in ws_hist.get_all_records()]
        row_idx = next((i + 2 for i, r in enumerate(hist_records) if r.get("month") == month), None)
        row_data = [month, round(income, 2), round(obligatory, 2), round(fun, 2),
                    round(one_time, 2), round(savings, 2), round(total_exp, 2), round(balance, 2)]
        if row_idx:
            ws_hist.update(f"A{row_idx}:H{row_idx}", [row_data])
        else:
            ws_hist.append_row(row_data)

    def get_dashboard_data(self) -> dict:
        now = datetime.datetime.now()
        month_str = now.strftime("%Y-%m")
        today_str = now.strftime("%d.%m.%Y")

        tx_ws = self._worksheet("transactions")
        all_tx = [self._normalize_tx_record(r) for r in tx_ws.get_all_records()]
        today_tx = [r for r in all_tx if r.get("date") == today_str]
        today_exp = sum(float(str(r.get("amount", 0)).replace(",", "."))
                        for r in today_tx if r.get("type") == "expense")

        plan = self.get_budget_plan(month_str)

        hist_ws = self._worksheet("history")
        history = [self._normalize_history_record(r) for r in hist_ws.get_all_records()]
        current_hist = next((h for h in history if h.get("month") == month_str), {})

        recent = list(reversed(all_tx))[:8]
        return {
            "period": month_str,
            "today_expense": round(today_exp, 2),
            "plan": plan,
            "fact": current_hist,
            "recent_tx": recent,
            "has_plan": bool(plan),
        }

    def get_available_months(self) -> list[str]:
        months: set[str] = set()

        try:
            tx_ws = self._worksheet("transactions")
            all_tx = [self._normalize_tx_record(r) for r in tx_ws.get_all_records()]
            for r in all_tx:
                m = str(r.get("month", "")).strip()
                if len(m) == 7 and m[4] == "-":
                    months.add(m)
        except Exception:
            pass

        try:
            ws = self._get_budget_ws()
            cell = (ws.acell("F1").value or "").strip()
            if "📅" in cell:
                cell = cell.replace("📅", "").strip()
            if len(cell) == 7 and cell[4] == "-":
                months.add(cell)
        except Exception:
            pass

        return sorted(months)

    def get_stats_by_month(self, month: str) -> dict:
        tx_ws = self._worksheet("transactions")
        all_tx = [self._normalize_tx_record(r) for r in tx_ws.get_all_records()]
        month_tx = [r for r in all_tx if str(r.get("month", "")) == month]

        def _to_float(value) -> float:
            try:
                if value is None:
                    return 0.0
                cleaned = str(value).replace(" ", "").replace(",", ".")
                return float(cleaned or 0)
            except Exception:
                return 0.0

        income = sum(_to_float(r.get("amount")) for r in month_tx if r.get("type") == "income")
        red = sum(_to_float(r.get("amount")) for r in month_tx
                  if r.get("type") == "expense" and r.get("category") in RED_ZONE_CATEGORIES)
        yellow = sum(_to_float(r.get("amount")) for r in month_tx
                     if r.get("type") == "expense" and r.get("category") in YELLOW_ZONE_CATEGORIES)
        green = sum(_to_float(r.get("amount")) for r in month_tx
                    if r.get("type") == "expense" and r.get("category") in GREEN_ZONE_CATEGORIES)
        savings = sum(_to_float(r.get("amount")) for r in month_tx if r.get("type") == "savings")

        total_expense = red + yellow + green
        balance = income - total_expense
        try:
            plan = self.get_budget_plan(month)
        except Exception:
            plan = {}

        recent = [
            r for r in reversed(all_tx)
            if str(r.get("month", "")) == month
        ][:10]

        return {
            "period": month,
            "plan": plan,
            "fact": {
                "month": month,
                "income": round(income, 2),
                "obligatory": round(red, 2),
                "fun": round(yellow, 2),
                "one_time": round(green, 2),
                "savings": round(savings, 2),
                "total_expenses": round(total_expense, 2),
                "balance": round(balance, 2),
            },
            "recent_tx": recent,
            "transactions_count": len(month_tx),
            "has_plan": bool(plan),
        }

    def get_spreadsheet_url(self) -> str:
        if self.sh:
            return f"https://docs.google.com/spreadsheets/d/{self.sh.id}"
        return ""
