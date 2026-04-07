"""Google Sheets integration for finance tracking — 3-zone budget system."""
import gspread
from google.oauth2.service_account import Credentials
import datetime
from typing import Optional
import styler

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


class FinanceSheets:
    def __init__(self, credentials_file: str, spreadsheet_name: str, currency: str = "EUR"):
        self.credentials_file = credentials_file
        self.spreadsheet_name = spreadsheet_name
        self.currency = currency
        self.gc = None
        self.sh = None
        self.creds = None

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

    def _init_spreadsheet(self):
        ws = self.sh.get_worksheet(0)
        ws.update_title("Транзакции")
        self._setup_tx_sheet(ws)
        ws2 = self.sh.add_worksheet("Бюджет", rows=60, cols=6)
        self._setup_budget_sheet(ws2)
        self.sh.add_worksheet("История", rows=100, cols=10)

    def _ensure_sheets(self):
        titles = [ws.title for ws in self.sh.worksheets()]
        if "Транзакции" not in titles:
            ws = self.sh.add_worksheet("Транзакции", rows=2000, cols=12)
            self._setup_tx_sheet(ws)
        if "Бюджет" not in titles:
            ws = self.sh.add_worksheet("Бюджет", rows=60, cols=6)
            self._setup_budget_sheet(ws)
        if "История" not in titles:
            ws = self.sh.add_worksheet("История", rows=100, cols=10)
            self._setup_history_sheet(ws)

    # ─── Sheet Setup ───────────────────────────────────────────────────────────

    def _setup_tx_sheet(self, ws):
        headers = ["Дата", "Тип", "Сумма", "Категория", "Описание", "Валюта",
                   "Неделя", "Месяц", "Квартал", "Полугодие", "Год", "Добавлено"]
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
        styler.apply_tx_styling(self.sh, ws)

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

    def _setup_budget_sheet(self, ws):
        """Три цветных блока бюджета + доходы/проекты."""
        L = self._get_row_layout()
        ws.freeze(rows=1)
        # Title row
        ws.update("A1:F1", [["Категория", "Лимит", "Факт (авто)", "Остаток", "Зона", "Примечание"]])
        ws.format("A1:F1", {
            "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })

        # 🔴 Red zone
        r_h = L["red_header"]
        ws.update(f"A{r_h}:F{r_h}", [["🔴 КРАСНАя ЗОНА — Обязательное", "", "", "", "", ""]])
        ws.format(f"A{r_h}:F{r_h}", {
            "backgroundColor": {"red": 0.95, "green": 0.8, "blue": 0.8},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.6, "green": 0.1, "blue": 0.1}},
        })
        for i, cat in enumerate(RED_ZONE_CATEGORIES):
            row = L["red_start"] + i
            ws.update(f"A{row}:F{row}", [[cat, 0, 0, f"=B{row}-C{row}", "red", ""]])
        ws.format(f"A{L['red_start']}:F{L['red_end']}", {
            "backgroundColor": {"red": 1.0, "green": 0.93, "blue": 0.93},
        })
        r_it = L["red_itogo"]
        ws.update(f"A{r_it}:F{r_it}", [["ИТОГО 🔴",
            f"=SUM(B{L['red_start']}:B{L['red_end']})",
            f"=SUM(C{L['red_start']}:C{L['red_end']})",
            f"=B{r_it}-C{r_it}", "", ""]])
        ws.format(f"A{r_it}:F{r_it}", {"textFormat": {"bold": True}})

        # 🟡 Yellow zone
        y_h = L["yellow_header"]
        ws.update(f"A{y_h}:F{y_h}", [["🟡 ЖЁЛТАЯ ЗОНА — Досуг, питание, гулянки", "", "", "", "", ""]])
        ws.format(f"A{y_h}:F{y_h}", {
            "backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.7},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.5, "green": 0.35, "blue": 0.0}},
        })
        for i, cat in enumerate(YELLOW_ZONE_CATEGORIES):
            row = L["yellow_start"] + i
            ws.update(f"A{row}:F{row}", [[cat, 0, 0, f"=B{row}-C{row}", "yellow", ""]])
        ws.format(f"A{L['yellow_start']}:F{L['yellow_end']}", {
            "backgroundColor": {"red": 1.0, "green": 0.98, "blue": 0.85},
        })
        y_it = L["yellow_itogo"]
        ws.update(f"A{y_it}:F{y_it}", [["ИТОГО 🟡",
            f"=SUM(B{L['yellow_start']}:B{L['yellow_end']})",
            f"=SUM(C{L['yellow_start']}:C{L['yellow_end']})",
            f"=B{y_it}-C{y_it}", "", ""]])
        ws.format(f"A{y_it}:F{y_it}", {"textFormat": {"bold": True}})

        # 🟢 Green zone
        g_h = L["green_header"]
        ws.update(f"A{g_h}:F{g_h}", [["🟢 ЗЕЛЁНАЯ ЗОНА — Разовые расходы", "", "", "", "", ""]])
        ws.format(f"A{g_h}:F{g_h}", {
            "backgroundColor": {"red": 0.8, "green": 0.95, "blue": 0.8},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.1, "green": 0.45, "blue": 0.1}},
        })
        for i, cat in enumerate(GREEN_ZONE_CATEGORIES):
            row = L["green_start"] + i
            ws.update(f"A{row}:F{row}", [[cat, 0, 0, f"=B{row}-C{row}", "green", ""]])
        ws.format(f"A{L['green_start']}:F{L['green_end']}", {
            "backgroundColor": {"red": 0.92, "green": 1.0, "blue": 0.92},
        })
        g_it = L["green_itogo"]
        ws.update(f"A{g_it}:F{g_it}", [["ИТОГО 🟢",
            f"=SUM(B{L['green_start']}:B{L['green_end']})",
            f"=SUM(C{L['green_start']}:C{L['green_end']})",
            f"=B{g_it}-C{g_it}", "", ""]])
        ws.format(f"A{g_it}:F{g_it}", {"textFormat": {"bold": True}})

        # 💰 Income + Projects block
        i_h = L["inc_header"]
        ws.update(f"A{i_h}:F{i_h}", [["💰 ДОХОДЫ И ПРОЕКТЫ", "", "", "", "", ""]])
        ws.format(f"A{i_h}:F{i_h}", {
            "backgroundColor": {"red": 0.8, "green": 0.85, "blue": 0.95},
            "textFormat": {"bold": True},
        })
        i_r = L["inc_row"]
        ws.update(f"A{i_r}:F{i_r}", [["Доход (план)", 0, 0, "", "", ""]])
        p_r = L["proj_row"]
        ws.update(f"A{p_r}:F{p_r}", [["💼 Бюджет проектов", 0, 0, "", "", "авто: 10% от расходов"]])
        ws.format(f"A{p_r}:F{p_r}", {
            "backgroundColor": {"red": 0.85, "green": 0.78, "blue": 0.95},
            "textFormat": {"bold": True},
        })

    def _setup_history_sheet(self, ws):
        headers = ["Месяц", "Доходы", "Обязательное", "Гулянки", "Разовые", "Всего расходов", "Баланс"]
        try:
            if ws.acell("A1").value == headers[0]:
                return
        except Exception:
            pass
        ws.update("A1:G1", [headers])
        ws.format("A1:G1", {
            "backgroundColor": {"red": 0.2, "green": 0.7, "blue": 0.3},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })
        ws.freeze(rows=1)

    # ─── Budget Plan Management ─────────────────────────────────────────────────

    def _get_budget_ws(self):
        return self.sh.worksheet("Бюджет")

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
        result = {"month": month, "red": {}, "yellow": 0, "green": 0, "income": 0}
        for i, cat in enumerate(RED_ZONE_CATEGORIES):
            row_idx = 3 + i  # 1-indexed → 0-indexed for list
            result["red"][cat] = float(all_vals[row_idx - 1][1] or 0)
        red_itogo = 3 + len(RED_ZONE_CATEGORIES)
        y_row = red_itogo + 3
        g_row = y_row + 3
        inc_row = g_row + 3
        result["yellow"] = float(all_vals[y_row - 1][1] or 0)
        result["green"] = float(all_vals[g_row - 1][1] or 0)
        result["income"] = float(all_vals[inc_row - 1][1] or 0)
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
        ws_tx = self.sh.worksheet("Транзакции")
        all_tx = ws_tx.get_all_records()
        month_tx = [r for r in all_tx if r.get("Месяц") == month]

        def _sum(cat_list, tx_type="Расход"):
            return sum(
                float(str(r.get("Сумма", 0)).replace(",", "."))
                for r in month_tx if r.get("Тип") == tx_type and r.get("Категория") in cat_list
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
        income_fact = _sum(INCOME_CATEGORIES, "Доход")
        ws_b.update(f"C{L['inc_row']}", [[round(income_fact, 2)]])

    # ─── Write transactions ─────────────────────────────────────────────────────

    def add_transaction(self, amount: float, category: str, description: str,
                        trans_type: str, trans_date: Optional[str] = None) -> dict:
        ws = self.sh.worksheet("Транзакции")
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
            trans_date, trans_type, round(float(amount), 2), category, description,
            self.currency, week_str, month_str, quarter_str, half_str, str(dt.year),
            now.strftime("%d.%m.%Y %H:%M"),
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

        # Auto-allocate 10% of every expense to project budget
        contribution = 0.0
        if trans_type == "Расход":
            contribution = round(float(amount) * 0.10, 2)
            self._add_to_project_budget(contribution)

        result = {
            "success": True,
            "date": trans_date,
            "type": trans_type,
            "amount": round(float(amount), 2),
            "category": category,
            "description": description,
            "zone": CATEGORY_TO_ZONE.get(category, "unknown"),
            "affected_month": month_str,  # caller should sync budget fact once
        }
        if contribution > 0:
            result["project_budget_contribution"] = contribution
        return result

    # ─── Search / Edit / Delete ─────────────────────────────────────────────────

    def search_transactions(self, query: str = "", limit: int = 10) -> list[dict]:
        ws = self.sh.worksheet("Транзакции")
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
        ws = self.sh.worksheet("Транзакции")
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
        ws = self.sh.worksheet("Транзакции")
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
        ws = self.sh.worksheet("Транзакции")
        all_values = ws.get_all_values()
        if row_id <= 1 or row_id > len(all_values):
            return {"success": False, "message": "Некорректный ID строки"}
        row = all_values[row_id - 1]
        if trans_date is not None: row[0] = trans_date
        if amount is not None: row[2] = str(round(float(amount), 2))
        if category is not None: row[3] = category
        if description is not None: row[4] = description
        ws.update(f"A{row_id}:K{row_id}", [row[:11]])
        month_str = row[7] if len(row) > 7 else datetime.datetime.now().strftime("%Y-%m")
        self._sync_history(month_str)
        self.update_budget_fact(month_str)
        return {"success": True, "message": "Успешно изменено"}

    # ─── Aggregations ───────────────────────────────────────────────────────────

    def _sync_history(self, month: str):
        records = self.sh.worksheet("Транзакции").get_all_records()
        month_records = [r for r in records if r.get("Месяц") == month]

        def _s(cat_filter=None, type_filter=None):
            return sum(
                float(str(r.get("Сумма", 0)).replace(",", "."))
                for r in month_records
                if (type_filter is None or r.get("Тип") == type_filter)
                and (cat_filter is None or r.get("Категория") in cat_filter)
            )

        income = _s(type_filter="Доход")
        obligatory = _s(cat_filter=RED_ZONE_CATEGORIES, type_filter="Расход")
        fun = _s(cat_filter=YELLOW_ZONE_CATEGORIES, type_filter="Расход")
        one_time = _s(cat_filter=GREEN_ZONE_CATEGORIES, type_filter="Расход")
        total_exp = obligatory + fun + one_time
        balance = income - total_exp

        ws_hist = self.sh.worksheet("История")
        hist_records = ws_hist.get_all_records()
        row_idx = next((i + 2 for i, r in enumerate(hist_records) if r.get("Месяц") == month), None)
        row_data = [month, round(income, 2), round(obligatory, 2), round(fun, 2),
                    round(one_time, 2), round(total_exp, 2), round(balance, 2)]
        if row_idx:
            ws_hist.update(f"A{row_idx}:G{row_idx}", [row_data])
        else:
            ws_hist.append_row(row_data)

    def get_dashboard_data(self) -> dict:
        now = datetime.datetime.now()
        month_str = now.strftime("%Y-%m")
        today_str = now.strftime("%d.%m.%Y")

        tx_ws = self.sh.worksheet("Транзакции")
        all_tx = tx_ws.get_all_records()
        today_tx = [r for r in all_tx if r.get("Дата") == today_str]
        today_exp = sum(float(str(r.get("Сумма", 0)).replace(",", "."))
                        for r in today_tx if r.get("Тип") == "Расход")

        plan = self.get_budget_plan(month_str)

        hist_ws = self.sh.worksheet("История")
        history = hist_ws.get_all_records()
        current_hist = next((h for h in history if h.get("Месяц") == month_str), {})

        recent = list(reversed(all_tx))[:8]
        return {
            "period": month_str,
            "today_expense": round(today_exp, 2),
            "plan": plan,
            "fact": current_hist,
            "recent_tx": recent,
            "has_plan": bool(plan),
        }

    def get_stats_by_month(self, month: str) -> dict:
        tx_ws = self.sh.worksheet("Транзакции")
        all_tx = tx_ws.get_all_records()
        month_tx = [r for r in all_tx if str(r.get("Месяц", "")) == month]

        def _to_float(value) -> float:
            try:
                if value is None:
                    return 0.0
                cleaned = str(value).replace(" ", "").replace(",", ".")
                return float(cleaned or 0)
            except Exception:
                return 0.0

        income = sum(_to_float(r.get("Сумма")) for r in month_tx if r.get("Тип") == "Доход")
        red = sum(_to_float(r.get("Сумма")) for r in month_tx
                  if r.get("Тип") == "Расход" and r.get("Категория") in RED_ZONE_CATEGORIES)
        yellow = sum(_to_float(r.get("Сумма")) for r in month_tx
                     if r.get("Тип") == "Расход" and r.get("Категория") in YELLOW_ZONE_CATEGORIES)
        green = sum(_to_float(r.get("Сумма")) for r in month_tx
                    if r.get("Тип") == "Расход" and r.get("Категория") in GREEN_ZONE_CATEGORIES)
        savings = sum(_to_float(r.get("Сумма")) for r in month_tx if r.get("Тип") == "Копилка")

        total_expense = red + yellow + green
        balance = income - total_expense
        plan = self.get_budget_plan(month)

        recent = [
            r for r in reversed(all_tx)
            if str(r.get("Месяц", "")) == month
        ][:10]

        return {
            "period": month,
            "plan": plan,
            "fact": {
                "Месяц": month,
                "Доходы": round(income, 2),
                "Обязательное": round(red, 2),
                "Гулянки": round(yellow, 2),
                "Разовые": round(green, 2),
                "Копилка": round(savings, 2),
                "Всего расходов": round(total_expense, 2),
                "Баланс": round(balance, 2),
            },
            "recent_tx": recent,
            "transactions_count": len(month_tx),
            "has_plan": bool(plan),
        }

    def get_spreadsheet_url(self) -> str:
        if self.sh:
            return f"https://docs.google.com/spreadsheets/d/{self.sh.id}"
        return ""
