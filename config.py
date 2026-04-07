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

# Voice transcription (optional)
TRANSCRIBE_API_KEY    = os.getenv("TRANSCRIBE_API_KEY", OPENROUTER_API_KEY)
TRANSCRIBE_MODEL      = os.getenv("TRANSCRIBE_MODEL", "mistralai/voxtral-small-24b-2507")
VOICE_DIRECT_MODE     = os.getenv("VOICE_DIRECT_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
VOICE_DIRECT_MODEL    = os.getenv("VOICE_DIRECT_MODEL", "google/gemini-3.1-flash-lite-preview")
DOCUMENT_MODEL        = os.getenv("DOCUMENT_MODEL", VOICE_DIRECT_MODEL)

# Comma-separated Telegram user IDs. Empty = allow all.
_raw = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS: list[int] = [int(x) for x in _raw.split(",") if x.strip()]
