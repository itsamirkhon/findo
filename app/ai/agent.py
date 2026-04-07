"""AI agent with OpenRouter function-calling."""
from __future__ import annotations
import json
import asyncio
import datetime
import re
from typing import AsyncIterator
import httpx
from app.prompts.system_prompt import build_finance_system_prompt
from app.services.sheets_service import (
    CATEGORY_ALIASES,
    CATEGORY_LABELS,
    FinanceSheets,
    GREEN_ZONE_CATEGORIES,
    INCOME_CATEGORIES,
    RED_ZONE_CATEGORIES,
    YELLOW_ZONE_CATEGORIES,
)

# Tools that mutate data — must not be executed more than once per user message
WRITE_TOOLS = {
    "add_expense",
    "add_income",
    "add_savings",
    "set_plan",
    "delete_transaction",
    "edit_transaction",
}

EXPENSE_CATEGORY_ENUM = [CATEGORY_LABELS["en"][category] for category in (RED_ZONE_CATEGORIES + YELLOW_ZONE_CATEGORIES + GREEN_ZONE_CATEGORIES)]
INCOME_CATEGORY_ENUM = [CATEGORY_LABELS["en"][category] for category in INCOME_CATEGORIES]
RED_LIMIT_PROPERTIES = {CATEGORY_LABELS["en"][category]: {"type": "number"} for category in RED_ZONE_CATEGORIES}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "Add an expense. Each purchased item must be a separate call. Never merge multiple purchases into one call. Categories: Red Zone (Rent, Education, Subscriptions, Communication, Health, Family Support, Sadaqah), Yellow Zone (Fun, Food), Green Zone (One-Time).",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount":      {"type": "number",  "description": "Amount"},
                    "category":    {"type": "string",  "enum": EXPENSE_CATEGORY_ENUM},
                    "description": {"type": "string",  "description": "Description"},
                    "trans_date":  {"type": "string",  "description": "Date in DD.MM.YYYY format (optional)"},
                },
                "required": ["amount", "category", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_income",
            "description": "Add an income transaction",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount":      {"type": "number",  "description": "Amount"},
                    "category":    {"type": "string",  "enum": INCOME_CATEGORY_ENUM},
                    "description": {"type": "string",  "description": "Description"},
                    "trans_date":  {"type": "string",  "description": "Date in DD.MM.YYYY format (optional)"},
                },
                "required": ["amount", "category", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_savings",
            "description": "Add money to savings",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount":      {"type": "number",  "description": "Amount"},
                    "description": {"type": "string",  "description": "What the savings are for or where they came from"},
                    "trans_date":  {"type": "string",  "description": "Date in DD.MM.YYYY format (optional)"},
                },
                "required": ["amount", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_plan",
            "description": "Set the monthly budget plan",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string", "description": "Month in YYYY-MM format"},
                    "income": {"type": "number", "description": "Expected income"},
                    "red_limits": {
                        "type": "object",
                        "description": "Red zone limits by category",
                        "properties": RED_LIMIT_PROPERTIES,
                    },
                    "yellow_limit": {"type": "number", "description": "Total yellow zone limit"},
                    "green_limit": {"type": "number", "description": "Green zone limit"},
                },
                "required": ["month", "income", "red_limits", "yellow_limit", "green_limit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_budget",
            "description": "Show the accumulated project budget (automatically 10% from every expense)",
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dashboard",
            "description": "Get the full dashboard (plan vs actual for the current month and statistics)",
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Get statistics for a specific month",
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
            "description": "Search transactions by pattern and return a list with row_id",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query by category, amount, or description. Leave empty to get the latest 10."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_transaction",
            "description": "Delete a specific transaction by its row ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "integer", "description": "Transaction row ID obtained via search_transactions"}
                },
                "required": ["row_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_transaction",
            "description": "Edit an existing transaction (amount, category, description, or date)",
            "parameters": {
                "type": "object",
                "properties": {
                    "row_id":      {"type": "integer", "description": "Row ID found via search_transactions"},
                    "amount":      {"type": "number",  "description": "New amount (optional)"},
                    "category":    {"type": "string",  "description": "New category (optional)"},
                    "description": {"type": "string",  "description": "New description (optional)"},
                    "trans_date":  {"type": "string",  "description": "New date in DD.MM.YYYY format (optional)"}
                },
                "required": ["row_id"]
            }
        }
    }
]


class FinanceAgent:
    def __init__(self, api_key: str, model: str, sheets: FinanceSheets,
                 currency: str = "EUR", language: str = "en"):
        self.api_key = api_key
        self.model = model
        self.sheets = sheets
        self.currency = currency
        self.language = language
        self.system_prompt = build_finance_system_prompt(currency, language)

    def _canonical_category(self, value: str) -> str:
        raw = str(value or "").strip()
        for canonical, aliases in CATEGORY_ALIASES.items():
            if raw in aliases:
                return canonical
        return raw

    def _normalize_red_limits(self, raw_limits: dict | None) -> dict:
        raw_limits = raw_limits or {}
        normalized: dict[str, float] = {}
        for key, value in raw_limits.items():
            normalized[self._canonical_category(key)] = value
        return normalized

    def update_preferences(self, *, model: str | None = None,
                           currency: str | None = None,
                           language: str | None = None):
        if model:
            self.model = model
        if currency:
            self.currency = currency
        if language:
            self.language = language
        self.system_prompt = build_finance_system_prompt(self.currency, self.language)

    def _normalize_stats_month(self, month: str | None) -> str:
        now = datetime.datetime.now()
        default_month = now.strftime("%Y-%m")
        if not month:
            return default_month

        raw = str(month).strip()
        m = re.match(r"^(\d{4})-(\d{1,2})$", raw)
        if not m:
            return default_month

        year = int(m.group(1))
        mon = int(m.group(2))
        if mon < 1 or mon > 12:
            return default_month

        normalized = f"{year:04d}-{mon:02d}"

        available = set()
        try:
            available = set(self.sheets.get_available_months())
        except Exception:
            available = set()

        if available and normalized not in available:
            candidates = [
                f"{now.year:04d}-{mon:02d}",
                f"{(now.year - 1):04d}-{mon:02d}",
                normalized,
            ]
            for c in candidates:
                if c in available:
                    return c

        if year < now.year - 1:
            return f"{now.year:04d}-{mon:02d}"

        return normalized

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
                return resp.get("content") or "Something went wrong. Please try again."

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

        return "I couldn't process the request. Please try again."

    def _run_tool(self, name: str, args: dict) -> dict:
        try:
            match name:
                case "add_expense":
                    return self.sheets.add_transaction(
                        amount=args["amount"], category=self._canonical_category(args["category"]),
                        description=args["description"], trans_type="Expense", trans_date=args.get("trans_date")
                    )
                case "add_income":
                    return self.sheets.add_transaction(
                        amount=args["amount"], category=self._canonical_category(args["category"]),
                        description=args["description"], trans_type="Income", trans_date=args.get("trans_date")
                    )
                case "add_savings":
                    return self.sheets.add_transaction(
                        amount=args["amount"], category="Копилка",
                        description=args["description"], trans_type="Savings", trans_date=args.get("trans_date")
                    )
                case "set_plan":
                    return self.sheets.set_budget_plan(
                        month=args["month"],
                        income=args["income"],
                        red_limits=self._normalize_red_limits(args["red_limits"]),
                        yellow_limit=args["yellow_limit"],
                        green_limit=args["green_limit"],
                    )
                case "get_project_budget":
                    return self.sheets.get_project_budget()
                case "get_dashboard":
                    return self.sheets.get_dashboard_data()
                case "get_stats":
                    month = self._normalize_stats_month(args.get("month"))
                    return self.sheets.get_stats_by_month(month)
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
                    result = {"error": "Duplicate: the same operation with identical data has already been executed"}
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
                elif tool_name in {"delete_transaction", "edit_transaction"} and isinstance(result, dict) and result.get("success"):
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
                "content": (
                    f"Подведи итог на языке `{self.language}`. "
                    "Ответь дружелюбным текстом, без JSON."
                ),
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
