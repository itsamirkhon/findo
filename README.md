# Findo

AI-powered Telegram finance assistant with Google Sheets as the source of truth.

Findo accepts natural-language expense and income messages, categorizes them into a 3-zone budget system, writes transactions into Google Sheets, and uses an AI agent to answer questions, analyze spending, and process receipts, PDFs, and voice notes.

## Highlights

- AI transaction parsing with tool-calling
- Google Sheets storage with automatic sheet/bootstrap setup
- 3-zone budgeting: red, yellow, green
- Receipt image and PDF extraction
- Voice transcription support
- Scheduled daily, weekly, and monthly summaries
- Runtime bot settings for language, currency, model, and timezone
- Structured Python package architecture

## Architecture

```text
findo/
├── app/
│   ├── __main__.py                 # `python -m app`
│   ├── ai/
│   │   └── agent.py               # OpenRouter agent, tool loop, prompt usage
│   ├── bot/
│   │   ├── application.py         # Thin public entrypoint
│   │   ├── bootstrap.py           # App wiring and Telegram handlers registration
│   │   ├── state.py               # Shared bot runtime state
│   │   ├── keyboards.py           # Telegram keyboards and settings UI text
│   │   ├── streaming.py           # Streaming reply rendering
│   │   ├── media.py               # Voice/image/PDF processing
│   │   └── handlers/
│   │       ├── onboarding.py      # `/start`, `/plan`, onboarding flow
│   │       ├── commands.py        # `/help`, `/sheet`, `/settings`, text messages
│   │       └── callbacks.py       # Inline button callbacks
│   ├── core/
│   │   ├── config.py              # `.env` loading
│   │   └── runtime.py             # Mutable runtime settings
│   ├── prompts/
│   │   └── system_prompt.py       # System prompts for the AI
│   ├── services/
│   │   ├── sheets_service.py      # Google Sheets data/service layer
│   │   ├── sheet_styler.py        # Google Sheets formatting
│   │   └── scheduler_service.py   # Scheduled summaries
│   └── utils/
│       └── markdown.py            # Markdown to Telegram HTML conversion
├── docs/
├── requirements.txt
├── .env.example
└── credentials.json               # Local only, not committed
```

## Core Flows

### 1. Text transaction flow
1. User sends a message in Telegram.
2. Telegram handler passes the message to the AI agent.
3. The agent decides which tool to call.
4. Tools write/read data through Google Sheets service.
5. Bot streams a human-readable response back to the user.

### 2. Receipt and document flow
1. User sends a photo or PDF.
2. Media handler extracts raw text via multimodal model or PDF parser.
3. Extracted text is forwarded back into the AI transaction flow.

### 3. Voice flow
1. User sends a voice note.
2. Bot transcribes audio.
3. Transcript is processed exactly like a text message.

## Budget Model

### Red zone
Mandatory expenses.

Categories:
`Аренда`, `Обучение`, `Подписки`, `Связь`, `Здоровье`, `Помощь семье`, `Садака`

### Yellow zone
Flexible lifestyle spending.

Categories:
`Гулянки`, `Питание`

### Green zone
One-time or irregular purchases.

Category:
`Разовые`

### Project budget
10% of every expense is automatically tracked as a separate project budget contribution.

## Google Sheets

Findo creates and maintains these sheets automatically:

- `Транзакции`: raw transaction ledger
- `Бюджет`: plan vs fact by category and zone
- `История`: monthly aggregates
- `Настройки`: persisted runtime settings

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key |
| `GOOGLE_CREDENTIALS_FILE` | Yes | Path to service account JSON |
| `SPREADSHEET_NAME` | Yes | Google Sheets file title |
| `AI_MODEL` | Yes | Default chat model |
| `CURRENCY` | Yes | Default currency code |
| `TIMEZONE` | No | Scheduler timezone |
| `LANGUAGE` | No | Default bot language |
| `ALLOWED_USERS` | No | Comma-separated Telegram user IDs |
| `TRANSCRIBE_API_KEY` | No | Voice transcription key |
| `TRANSCRIBE_MODEL` | No | Speech-to-text model |
| `VOICE_DIRECT_MODE` | No | Use direct multimodal audio transcription first |
| `VOICE_DIRECT_MODEL` | No | Multimodal voice model |
| `DOCUMENT_MODEL` | No | Multimodal receipt/document model |
| `GOOGLE_CREDENTIALS_JSON` | No | Railway/cloud alternative to local credentials file |

## Run Locally

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app
```

## Development Notes

### When adding a new expense category
1. Update category lists in `app/services/sheets_service.py`.
2. Update the `add_expense` tool schema in `app/ai/agent.py`.
3. Update category rules in `app/prompts/system_prompt.py`.
4. Remove the existing `Бюджет` sheet so the bot can recreate it with the new layout.

### When changing runtime settings behavior
Check these modules together:
- `app/core/runtime.py`
- `app/bot/keyboards.py`
- `app/bot/handlers/commands.py`
- `app/bot/handlers/callbacks.py`

## Docs

- [English onboarding](docs/ONBOARDING_EN.md)
- [Русский onboarding](docs/ONBOARDING_RU.md)
- [Railway deploy guide](docs/DEPLOY_RAILWAY.md)

## Security

Never commit:
- `.env`
- `credentials.json`
- raw service-account JSON

## License

MIT. See [LICENSE](LICENSE).
