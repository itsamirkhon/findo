"""AI agent with OpenRouter function-calling."""
from __future__ import annotations
import json
import asyncio
from typing import AsyncIterator
import httpx
from sheets import FinanceSheets

# Tools that mutate data — must not be executed more than once per user message
WRITE_TOOLS = {"add_expense", "add_income", "add_savings", "set_plan",
               "delete_transaction", "delete_last", "edit_transaction"}

def _build_system_prompt(currency: str = "EUR") -> str:
    return f"""Ты — личный финансовый ИИ-ассистент Амирхона. Валюта: **{currency}**.
Ведёшь учёт доходов, расходов и бюджета в Google Sheets по системе трёх цветных зон.

🔴 КРАСНАЯ ЗОНА — обязательные расходы (нельзя пропускать):
  Категории: Аренда, Обучение, Подписки, Связь, Здоровье, Помощь семье, Садака

🟡 ЖЁЛТАЯ ЗОНА — досуг, питание, гулянки:
  Категории: Гулянки, Питание

🟢 ЗЕЛЁНАЯ ЗОНА — разовые/непредвиденные расходы:
  Категория: Разовые

💰 ДОХОДЫ бывают: Зарплата, Фриланс, Прочее

Правила:
- Общайся только на русском языке, используй эмодзи
- Всегда указывай суммы с знаком валюты: {currency} (не рубли, не доллары!)
- При вводе расхода — распредели в нужную зону автоматически
- При слове «обед», «ресторан», «кофе», «бар», «встреча» → Гулянки 🟡
- При слове «хлеб», «еда», «продукты», «магазин», «кафе», «супермаркет» → Питание 🟡
- При слове «аренда», «счёт», «школа», «интернет», «лекарство», «линзы», «аптека» → соответствующая Красная категория 🔴
- При слове «куртка», «телефон», «ремонт», «одежда», «техника» → Разовые 🟢
- ❗ Не выдумывай новые категории. Используй только те, что перечислены выше.
- ❗❗ Если пользователь упомянул несколько покупок — вызывай add_expense ОТДЕЛЬНО для каждой! Никогда не следуй суммы.
- После записи расхода — пиши красивый текст И упомяни: «💼 +X{currency} в Бюджет проектов (10% авто)» где X = 10% от суммы
- Не возвращай JSON-ответ никогда!
- Если Жёлтая зона использована >80% — предупреди!
- ❗ Перед удалением/изменением — всегда сначала вызови search_transactions чтобы узнать row_id. Не угадывай row_id из памяти!
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "Добавить расход. Каждый товар/покупка = отдельный вызов. Нельзя слагать несколько покупок в одну! Категории: Красная (Аренда/Обучение/Подписки/Связь/Здоровье/Помощь семье/Садака), Жёлтая (Гулянки/Питание), Зелёная (Разовые)",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount":      {"type": "number",  "description": "Сумма"},
                    "category":    {"type": "string",  "enum": [
                        "Аренда", "Обучение", "Подписки", "Связь",
                        "Здоровье", "Помощь семье", "Садака",
                        "Гулянки", "Питание", "Разовые"
                    ]},
                    "description": {"type": "string",  "description": "Описание"},
                    "trans_date":  {"type": "string",  "description": "Дата ДД.ММ.ГГГГ (опционально)"},
                },
                "required": ["amount", "category", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_income",
            "description": "Добавить доход",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount":      {"type": "number",  "description": "Сумма"},
                    "category":    {"type": "string",  "enum": ["Зарплата", "Фриланс", "Прочее"]},
                    "description": {"type": "string",  "description": "Описание"},
                    "trans_date":  {"type": "string",  "description": "Дата ДД.ММ.ГГГГ (опционально)"},
                },
                "required": ["amount", "category", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_savings",
            "description": "Отложить в копилку",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount":      {"type": "number",  "description": "Сумма"},
                    "description": {"type": "string",  "description": "На что отложили или откуда"},
                    "trans_date":  {"type": "string",  "description": "Дата ДД.ММ.ГГГГ (опционально)"},
                },
                "required": ["amount", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_plan",
            "description": "Поставить план бюджета на месяц",
            "parameters": {
                "type": "object",
                "properties": {
                    "month":        {"type": "string", "description": "Месяц в формате YYYY-MM"},
                    "salary":       {"type": "number", "description": "Ожидаемая зарплата/доход"},
                    "obligatory":   {"type": "number", "description": "Обязательные расходы"},
                    "fun":          {"type": "number", "description": "Гулянки/развлечения"},
                    "one_time":     {"type": "number", "description": "Разовые крупные покупки"},
                    "savings_goal": {"type": "number", "description": "Цель по копилке"},
                },
                "required": ["month", "salary", "obligatory", "fun", "one_time", "savings_goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_budget",
            "description": "Показать накопленный Бюджет проектов (автоматически 10% от каждого расхода)",
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dashboard",
            "description": "Получить полный дашборд (План/Факт за текущий месяц и статистику)",
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Статистика за определенный месяц",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string", "description": "YYYY-MM"},
                },
                "required": ["month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": "Поиск транзакций по паттерну, возвращает список с row_id",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос (категория, сумма или описание). Оставьте пустым чтобы получить 10 последних."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_transaction",
            "description": "Удалить конкретную транзакцию по её ID строки (row_id)",
            "parameters": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "integer", "description": "ID строки транзакции, полученный через search_transactions"}
                },
                "required": ["row_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_transaction",
            "description": "Изменить существующую транзакцию (сумму, категорию, описание, дату)",
            "parameters": {
                "type": "object",
                "properties": {
                    "row_id":      {"type": "integer", "description": "ID строки (найти через search_transactions)"},
                    "amount":      {"type": "number",  "description": "Новая сумма (опционально)"},
                    "category":    {"type": "string",  "description": "Новая категория (опционально)"},
                    "description": {"type": "string",  "description": "Новое описание (опционально)"},
                    "trans_date":  {"type": "string",  "description": "Новая дата ДД.ММ.ГГГГ (опционально)"}
                },
                "required": ["row_id"]
            }
        }
    }
]


class FinanceAgent:
    def __init__(self, api_key: str, model: str, sheets: FinanceSheets, currency: str = "EUR"):
        self.api_key = api_key
        self.model = model
        self.sheets = sheets
        self.currency = currency
        self.system_prompt = _build_system_prompt(currency)

    async def process(self, user_message: str, history: list | None = None, is_job: bool = False) -> str:
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history[-16:])   # last 8 turns
            
        if is_job:
            # When triggered by scheduler
            messages.append({"role": "user", "content": user_message})
        else:
            messages.append({"role": "user", "content": user_message})

        for _ in range(4):
            resp = await self._call_api(messages)
            tool_calls = resp.get("tool_calls") or []
            if not tool_calls:
                return resp.get("content") or "Произошла ошибка, попробуйте снова."

            messages.append({
                "role": "assistant",
                "content": resp.get("content"),
                "tool_calls": tool_calls,
            })
            
            for tc in tool_calls:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except Exception:
                    args = {}
                result = self._run_tool(tc["function"]["name"], args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

        return "Не удалось обработать запрос. Попробуйте ещё раз."

    def _run_tool(self, name: str, args: dict) -> dict:
        try:
            match name:
                case "add_expense":
                    return self.sheets.add_transaction(
                        amount=args["amount"], category=args["category"],
                        description=args["description"], trans_type="Расход", trans_date=args.get("trans_date")
                    )
                case "add_income":
                    return self.sheets.add_transaction(
                        amount=args["amount"], category=args["category"],
                        description=args["description"], trans_type="Доход", trans_date=args.get("trans_date")
                    )
                case "add_savings":
                    return self.sheets.add_transaction(
                        amount=args["amount"], category="Копилка",
                        description=args["description"], trans_type="Копилка", trans_date=args.get("trans_date")
                    )
                case "set_plan":
                    return self.sheets.set_budget_plan(
                        month=args["month"],
                        income=args["income"],
                        red_limits=args["red_limits"],
                        yellow_limit=args["yellow_limit"],
                        green_limit=args["green_limit"],
                    )
                case "get_project_budget":
                    return self.sheets.get_project_budget()
                case "get_dashboard":
                    return self.sheets.get_dashboard_data()
                case "get_stats":
                    return self.sheets.get_stats_by_month(args["month"])
                case "search_transactions":
                    return {"transactions": self.sheets.search_transactions(query=args.get("query", ""))}
                case "delete_transaction":
                    return self.sheets.delete_transaction(row_id=args["row_id"])
                case "edit_transaction":
                    return self.sheets.edit_transaction(
                        row_id=args["row_id"],
                        amount=args.get("amount"),
                        category=args.get("category"),
                        description=args.get("description"),
                        trans_date=args.get("trans_date")
                    )
                case _:
                    return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}

    async def _call_api(self, messages: list, with_tools: bool = True) -> dict:
        body: dict = {
            "model": self.model,
            "messages": messages,
        }
        if with_tools:
            body["tools"] = TOOLS
            body["tool_choice"] = "auto"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://finance-tgbot.app",
                    "X-Title": "Finance TG Bot",
                },
                json=body,
            )
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            return {"content": msg.get("content", ""), "tool_calls": msg.get("tool_calls", [])}

    async def process_stream(self, user_message: str, history: list | None = None) -> AsyncIterator[str]:
        """Execute tool calls, then request a plain-text response WITHOUT tools.
        
        Pattern:
          1. Loop with tools enabled until no more tool_calls
          2. If text looks like JSON or is empty, make one final call WITHOUT tools
             to guarantee a human-readable response
          3. Yield result word-by-word (simulated stream, no extra latency)
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history[-16:])
        messages.append({"role": "user", "content": user_message})

        executed_writes: set[str] = set()
        affected_months: set[str] = set()  # months that need budget sync after all tools run
        any_tools_ran = False
        final_text = ""

        # Phase 1: execute tool calls
        for _ in range(6):
            resp = await self._call_api(messages, with_tools=True)
            tool_calls = resp.get("tool_calls") or []
            if not tool_calls:
                final_text = resp.get("content") or ""
                break

            any_tools_ran = True
            messages.append({
                "role": "assistant",
                "content": resp.get("content"),
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except Exception:
                    args = {}

                # Dedup by tool_name + args fingerprint (not just tool_name)
                # This allows recording хлеб 4€ AND вода 2€ in one message,
                # but blocks identical duplicate calls like хлеб 4€ × 4 times
                sig = f"{tool_name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
                if tool_name in WRITE_TOOLS and sig in executed_writes:
                    result = {"error": "Дубль: эта операция с теми же данными уже выполнена"}
                else:
                    result = self._run_tool(tool_name, args)
                    if tool_name in WRITE_TOOLS:
                        executed_writes.add(sig)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
                # Track months affected by write operations for deferred sync
                if tool_name in {"add_expense", "add_income", "add_savings"} and isinstance(result, dict):
                    if m := result.get("affected_month"):
                        affected_months.add(m)
                elif tool_name in {"delete_transaction", "delete_last", "edit_transaction"} and isinstance(result, dict) and result.get("success"):
                    import datetime as _dt
                    affected_months.add(_dt.datetime.now().strftime("%Y-%m"))

        # Phase 1.5: sync budget sheet ONCE for all affected months (fire-and-forget)
        # We don't await this — it runs in background so the user gets a response fast
        if affected_months:
            _months_copy = set(affected_months)
            _sheets = self.sheets

            async def _bg_sync():
                for _m in _months_copy:
                    try:
                        _sheets._sync_history(_m)
                    except Exception:
                        pass
                    try:
                        _sheets.update_budget_fact(_m)
                    except Exception:
                        pass

            asyncio.create_task(_bg_sync())

        # Phase 2: if tools ran and final_text looks like JSON (or is empty),
        # make one more call WITHOUT tools to get human-readable text
        _text = final_text.strip()
        if any_tools_ran and (not _text or _text.startswith("{") or _text.startswith("[")):
            messages.append({
                "role": "user",
                "content": "Подведи итог на русском. Ответь дружельным текстом, без JSON.",
            })
            try:
                resp2 = await self._call_api(messages, with_tools=False)
                final_text = resp2.get("content") or "Операция выполнена ✅"
            except Exception:
                final_text = "Операция выполнена ✅"

        if not final_text:
            final_text = "Операция выполнена."

        # Phase 3: yield word by word
        words = final_text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            if i % 5 == 0:
                await asyncio.sleep(0.01)
