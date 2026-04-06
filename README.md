# 💰 Findo — AI-powered Telegram Finance Assistant

A personal finance management Telegram bot with AI agent, Google Sheets integration, and a 3-zone budget system (🔴 Red / 🟡 Yellow / 🟢 Green).

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21.6-blue.svg)](https://python-telegram-bot.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ Features

- 🤖 **AI Agent** — understands natural language (e.g. *"bought bread for 4 and water for 2"*)
- 📊 **Google Sheets** — all data stored in your own private spreadsheet
- 🎯 **3-Zone Budget System**
  - 🔴 **Red** — mandatory fixed expenses (rent, subscriptions, health...)
  - 🟡 **Yellow** — food, dining, entertainment
  - 🟢 **Green** — one-time / unexpected expenses
- 💼 **Project Budget** — automatically saves 10% of every expense
- 📅 **Monthly Planning** — set limits per category via `/plan`
- 📈 **Dashboard** — real-time plan vs. actual comparison
- 🔔 **Scheduled Reports** — daily / weekly / monthly summaries
- 💬 **Fully in Russian** — designed for Russian-speaking users (easily adaptable)

---

## 🗂 Project Structure

```
findo/
├── bot.py              # Telegram bot — handlers, commands, message routing
├── agent.py            # AI agent — OpenRouter function calling, tool loop
├── sheets.py           # Google Sheets — read/write transactions, budget sync
├── scheduler.py        # Scheduled tasks — daily/weekly/monthly reports
├── styler.py           # Google Sheets visual formatting (colors, freeze rows)
├── config.py           # Config loader from .env
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
└── credentials.json    # ← YOU CREATE THIS (Google Service Account key)
```

---

## 🚀 Setup Guide (Onboarding)

We've prepared highly detailed, step-by-step onboarding documents for beginners. 
Please choose your preferred language:

- 🇬🇧 **[Detailed Setup Guide (English)](docs/ONBOARDING_EN.md)**
- 🇷🇺 **[Подробная инструкция (Русский)](docs/ONBOARDING_RU.md)**

*These guides explain everything from creating a Telegram bot to configuring Google Cloud & OpenRouter, completely from scratch. **Includes a guide on how to host the bot 24/7 for free!***

---

## 📱 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + quick start guide |
| `/plan` | Set monthly budget limits (income + zones) |
| `/dashboard` | View current month plan vs. actual |
| `/stats` | Spending statistics |
| `/transactions` | View recent transactions |
| `/help` | Full command list |

**Natural language examples:**
```
"Купил хлеб за 3 евро"
"Оплатил аренду 500 EUR"
"Сегодня потратил на кофе 4 и обед 12"
"Удали последнюю транзакцию"
"Сколько у меня бюджет на проекты?"
"Покажи мои расходы за эту неделю"
```

---

## 🎯 Budget Zone System

The bot categorizes all expenses into one of three zones:

### 🔴 Red Zone — Mandatory Fixed Expenses
> Categories: `Аренда`, `Обучение`, `Подписки`, `Связь`, `Здоровье`, `Помощь семье`, `Садака`

These are non-negotiable expenses that must be paid every month. Set a strict limit.

### 🟡 Yellow Zone — Lifestyle & Food
> Categories: `Гулянки` (dining out / entertainment), `Питание` (groceries / food)

Flexible expenses — dining, cafes, restaurants, groceries. Monitor these carefully.

### 🟢 Green Zone — One-Time / Unexpected
> Category: `Разовые`

Clothing, electronics, repairs, travel — anything irregular.

### 💼 Project Budget
Automatically accumulates **10% of every expense** into a dedicated "project budget" cell. Tracks how much you could invest in personal projects.

---

## 🗄 Google Sheets Structure

The bot creates and manages three sheets automatically:

### Транзакции (Transactions)
| Дата | Тип | Сумма | Категория | Описание | Валюта | Неделя | Месяц | Квартал | ... |
|------|-----|-------|-----------|----------|--------|--------|-------|---------|-----|

### Бюджет (Budget)
Color-coded table with: Категория | Лимит | Факт (авто) | Остаток | Зона

- 🔴 Red zone rows
- 🟡 Yellow zone rows (Гулянки + Питание)
- 🟢 Green zone rows
- 💰 Income + Project Budget rows

### История (History)
Monthly rollup: income, zone totals, balance per month.

---

## ⚙️ Configuration Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot token from @BotFather |
| `OPENROUTER_API_KEY` | ✅ | API key from openrouter.ai |
| `AI_MODEL` | ✅ | Model ID (e.g. `google/gemini-flash-1.5`) |
| `GOOGLE_CREDENTIALS_FILE` | ✅ | Path to service account JSON |
| `SPREADSHEET_NAME` | ✅ | Name of your Google Spreadsheet |
| `CURRENCY` | ✅ | Currency symbol: `EUR`, `USD`, `RUB`, `UZS` |
| `ALLOWED_USERS` | ❌ | Comma-separated user IDs. Empty = public |

---

## 🤖 Supported AI Models

Any model on [OpenRouter](https://openrouter.ai/models) that supports function calling:

| Model | Speed | Cost | Notes |
|-------|-------|------|-------|
| `google/gemini-flash-1.5` | ⚡ Fast | 💚 Free tier | Recommended |
| `google/gemini-pro-1.5` | 🔵 Medium | 💛 Low | More capable |
| `openai/gpt-4o-mini` | ⚡ Fast | 💛 Low | Good quality |
| `anthropic/claude-3-haiku` | 🔵 Medium | 💛 Low | Excellent reasoning |
| `mistralai/mistral-7b-instruct` | ⚡ Fast | 💚 Very cheap | Budget option |

---

## 🔒 Security Notes

- **`credentials.json`** contains your Google service account private key — **never share or commit it**
- **`.env`** contains all your API keys — **never share or commit it**
- Both files are in `.gitignore` by default
- `ALLOWED_USERS` restricts who can interact with your bot

---

## 🛠 Development

### Running locally
```bash
source venv/bin/activate
python bot.py
```

### Updating the spreadsheet structure
If you change zone categories in `sheets.py`, the existing **Бюджет** sheet must be deleted manually from Google Sheets — the bot will recreate it with the new structure on next startup.

### Adding a new expense category
1. Edit `sheets.py` → add to the appropriate `*_ZONE_CATEGORIES` list
2. Edit `agent.py` → add to the `enum` in the `add_expense` tool definition
3. Edit `agent.py` → update system prompt rules for the new category
4. Delete the **Бюджет** sheet in Google Sheets (will be recreated automatically)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file for details.

---

## 🙏 Credits

Built with:
- [python-telegram-bot](https://python-telegram-bot.org/) — Telegram Bot API wrapper
- [gspread](https://gspread.readthedocs.io/) — Google Sheets Python API
- [OpenRouter](https://openrouter.ai/) — Unified AI API gateway
- [APScheduler](https://apscheduler.readthedocs.io/) — Scheduled tasks
