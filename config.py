import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENROUTER_API_KEY    = os.getenv("OPENROUTER_API_KEY", "")
GOOGLE_CREDENTIALS    = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_NAME      = os.getenv("SPREADSHEET_NAME", "Финансовый учёт")
CURRENCY              = os.getenv("CURRENCY", "EUR")
AI_MODEL              = os.getenv("AI_MODEL", "openai/gpt-4o-mini")
TIMEZONE              = os.getenv("TIMEZONE", "Europe/Moscow")

# Comma-separated Telegram user IDs. Empty = allow all.
_raw = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS: list[int] = [int(x) for x in _raw.split(",") if x.strip()]
