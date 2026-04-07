"""Telegram bot entry-point."""
import logging
import datetime
import os
import tempfile
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
    ConversationHandler,
)
import httpx
import config
from sheets import FinanceSheets, RED_ZONE_CATEGORIES
from agent import FinanceAgent
from scheduler import register_jobs
import re, html as htmllib

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)
OPENROUTER_TRANSCRIBE_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def md_to_html(text: str) -> str:
    """Convert AI Markdown output to Telegram-safe HTML."""
    # 1. Escape HTML special chars in non-code segments
    # Process code blocks first to protect them
    parts = re.split(r'(```[\s\S]*?```|`[^`]+`)', text)
    result = []
    for i, part in enumerate(parts):
        if part.startswith('```'):
            # Fenced code block
            inner = re.sub(r'^```\w*\n?', '', part)
            inner = re.sub(r'\n?```$', '', inner)
            result.append(f'<pre><code>{htmllib.escape(inner)}</code></pre>')
        elif part.startswith('`') and part.endswith('`') and len(part) > 2:
            # Inline code
            result.append(f'<code>{htmllib.escape(part[1:-1])}</code>')
        else:
            p = htmllib.escape(part)
            # Headers: ### → bold
            p = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', p, flags=re.MULTILINE)
            # Bold: **text** or __text__
            p = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', p)
            p = re.sub(r'__(.+?)__', r'<b>\1</b>', p)
            # Italic: *text* or _text_ (not inside words)
            p = re.sub(r'(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)', r'<i>\1</i>', p)
            p = re.sub(r'(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)', r'<i>\1</i>', p)
            # Strikethrough: ~~text~~
            p = re.sub(r'~~(.+?)~~', r'<s>\1</s>', p)
            # Inline links: [text](url)
            p = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', p)
            # Markdown tables → monospace
            def fmt_table(m):
                lines = [l.strip() for l in m.group(0).strip().splitlines() if l.strip()]
                rows = []
                for l in lines:
                    if re.match(r'^[\|\s\-:]+$', l):  # separator row
                        continue
                    cells = [c.strip() for c in l.strip('|').split('|')]
                    rows.append('  '.join(f'{c:<14}' for c in cells))
                return '<pre>' + '\n'.join(rows) + '</pre>'
            p = re.sub(
                r'((?:^\|.+\|\s*\n?)+)',
                fmt_table, p, flags=re.MULTILINE
            )
            # Horizontal rule
            p = re.sub(r'^[-*_]{3,}$', '─────────────────', p, flags=re.MULTILINE)
            # Bullet points already look fine with •, just ensure they render
            result.append(p)
    return ''.join(result)


sheets = FinanceSheets(config.GOOGLE_CREDENTIALS, config.SPREADSHEET_NAME, config.CURRENCY)
agent: FinanceAgent | None = None
histories: dict[int, list] = {}

# Minimum edit interval to avoid Telegram flood limits (seconds)
STREAM_EDIT_INTERVAL = 1.5

# ConversationHandler states
ONB_INCOME, ONB_RED, ONB_YELLOW, ONB_GREEN = range(4)

def allowed(uid: int) -> bool:
    return not config.ALLOWED_USERS or uid in config.ALLOWED_USERS

def main_keyboard() -> InlineKeyboardMarkup:
    url = sheets.get_spreadsheet_url()
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Дашборд",           callback_data="dashboard"),
            InlineKeyboardButton("📈 План vs Факт",      callback_data="plan"),
        ],
        [
            InlineKeyboardButton("📅 Статистика месяца", callback_data="stats"),
            InlineKeyboardButton("📁 Открыть таблицу",    url=url),
        ],
    ])

def _current_month() -> str:
    return datetime.datetime.now().strftime("%Y-%m")

def _month_label() -> str:
    months = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    now = datetime.datetime.now()
    return f"{months[now.month]} {now.year}"

# ─── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END
    # Check if budget plan exists for current month
    month = _current_month()
    if not sheets.has_budget_for_month(month):
        await update.message.reply_text(
            f"🗓 *Настройка бюджета на {_month_label()}*\n\n"
            "Для тебя ещё не заполнен план на этот месяц. Давай настроим!\n\n"
            "👉 *Шаг 1/4:* Какой ожидаемый доход в этом месяце? (EUR)",
            parse_mode="Markdown"
        )
        return ONB_INCOME
    await _send_welcome(update)
    return ConversationHandler.END

async def _send_welcome(update: Update):
    await update.message.reply_text(
        "👋 *Финансовый ИИ-ассистент*\n\n"
        "Просто пиши в свободной форме:\n"
        "• «Потратил 15€ на обед»\n"
        "• «Получил зарплату 2500€»\n"
        "• «Удали расход на кофе вчера»\n"
        "• «Покажи дашборд»\n\n"
        "Данные сохраняются в *Google Sheets* 📊",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

# ─── Onboarding ConversationHandler ───────────────────────────────────────────

async def onb_income(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["onb_income"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введи число. Например: `2000`", parse_mode="Markdown")
        return ONB_INCOME
    cats = ", ".join(RED_ZONE_CATEGORIES)
    await update.message.reply_text(
        f"✅ Доход: {ctx.user_data['onb_income']}€\n\n"
        f"👉 *Шаг 2/4:* Лимиты Красной зоны 🔴\n"
        f"Категории: `{cats}`\n\n"
        f"Введи суммы через запятую (в том же порядке):\n"
        f"Пример: `467, 50, 17, 11, 30, 100, 20`",
        parse_mode="Markdown"
    )
    return ONB_RED

async def onb_red(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        vals = [float(v.strip()) for v in update.message.text.split(",")]
        if len(vals) != len(RED_ZONE_CATEGORIES):
            raise ValueError
        ctx.user_data["onb_red"] = dict(zip(RED_ZONE_CATEGORIES, vals))
    except (ValueError, IndexError):
        await update.message.reply_text(
            f"❌ Нужно {len(RED_ZONE_CATEGORIES)} чисел через запятую. Пример: `467, 50, 17, 11, 30, 100, 20`",
            parse_mode="Markdown"
        )
        return ONB_RED
    total_red = sum(ctx.user_data["onb_red"].values())
    await update.message.reply_text(
        f"✅ Красная зона: {total_red}€\n\n"
        f"👉 *Шаг 3/4:* Лимит Жёлтой зоны 🟡 (Гулянки/рестораны)?\n"
        f"Пример: `150`",
        parse_mode="Markdown"
    )
    return ONB_YELLOW

async def onb_yellow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["onb_yellow"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Введи число. Например: `150`", parse_mode="Markdown")
        return ONB_YELLOW
    await update.message.reply_text(
        f"✅ Жёлтая зона: {ctx.user_data['onb_yellow']}€\n\n"
        f"👉 *Шаг 4/4:* Лимит Зелёной зоны 🟢 (Разовые покупки)?\n"
        f"Пример: `200`",
        parse_mode="Markdown"
    )
    return ONB_GREEN

async def onb_green(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["onb_green"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Введи число. Например: `200`", parse_mode="Markdown")
        return ONB_GREEN

    month = _current_month()
    try:
        sheets.set_budget_plan(
            month=month,
            income=ctx.user_data["onb_income"],
            red_limits=ctx.user_data["onb_red"],
            yellow_limit=ctx.user_data["onb_yellow"],
            green_limit=ctx.user_data["onb_green"],
        )
        await update.message.reply_text(
            f"🎉 *План на {_month_label()} записан!*\n\n"
            f"🔴 Красная: {sum(ctx.user_data['onb_red'].values()):.0f}€\n"
            f"🟡 Жёлтая: {ctx.user_data['onb_yellow']:.0f}€\n"
            f"🟢 Зелёная: {ctx.user_data['onb_green']:.0f}€\n"
            f"💰 Доход (план): {ctx.user_data['onb_income']:.0f}€\n\n"
            "Начинаем учёт! Вводи расходы в свободной форме 💬",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка записи плана: {e}")
    return ConversationHandler.END

async def onb_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Настройка отменена.", reply_markup=main_keyboard())
    return ConversationHandler.END

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "🤖 *Доступные команды*\n\n"
        "/start   — главное меню\n"
        "/sheet   — ссылка на Google Sheets\n"
        "/table   — ссылка на Google Sheets\n"
        "/clear   — сбросить историю диалога\n"
        "/help    — эта справка\n\n"
        "*Примеры фраз:*\n"
        "💸 «Потратил 8.50 на кофе из категории развлечений»\n"
        "💰 «500 зарплата за проект»\n"
        "📊 «Покажи статистику за этот месяц»\n"
        "🎤 Голосовые тоже поддерживаются (распознаю и обработаю как текст)\n"
        "🧾 Можно отправить фото чека или PDF-инвойс — распознаю и внесу операции\n",
        parse_mode="Markdown",
    )

async def cmd_sheet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        return
    await update.message.reply_text(f"📁 Твоя таблица:\n{sheets.get_spreadsheet_url()}")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        return
    histories[update.effective_user.id] = []
    await update.message.reply_text("🗑 История диалога очищена.")

# ─── Message & callback handlers ───────────────────────────────────────────────

async def cmd_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Manually trigger onboarding."""
    if not allowed(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        f"🗓 *Настройка бюджета на {_month_label()}*\n\n"
        "Шаг 1/4: Какой ожидаемый доход в этом месяце? (EUR)",
        parse_mode="Markdown"
    )
    return ONB_INCOME

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await _reply_agent_stream(update, update.message.text)

async def _transcribe_voice_file(file_path: str) -> str:
    if not config.TRANSCRIBE_API_KEY:
        raise RuntimeError("TRANSCRIBE_API_KEY is not set")

    headers = {"Authorization": f"Bearer {config.TRANSCRIBE_API_KEY}"}
    data = {"model": config.TRANSCRIBE_MODEL}

    with open(file_path, "rb") as audio_file:
        files = {"file": (os.path.basename(file_path), audio_file, "audio/ogg")}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                OPENROUTER_TRANSCRIBE_URL,
                headers=headers,
                data=data,
                files=files,
            )
            resp.raise_for_status()

    payload = resp.json()
    return (payload.get("text") or "").strip()

async def _transcribe_voice_direct(file_path: str) -> str:
    if not config.TRANSCRIBE_API_KEY:
        raise RuntimeError("TRANSCRIBE_API_KEY is not set")

    with open(file_path, "rb") as audio_file:
        encoded = base64.b64encode(audio_file.read()).decode("utf-8")

    body = {
        "model": config.VOICE_DIRECT_MODEL,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Транскрибируй голосовое сообщение дословно. Верни только распознанный текст без комментариев.",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": encoded,
                            "format": "ogg",
                        },
                    },
                ],
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {config.TRANSCRIBE_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(OPENROUTER_CHAT_URL, headers=headers, json=body)
        resp.raise_for_status()

    payload = resp.json()
    message = (payload.get("choices") or [{}])[0].get("message", {})
    content = message.get("content", "")

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        content = " ".join(text_parts)

    return str(content).strip()

async def _extract_text_from_image_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{encoded}"

    body = {
        "model": config.DOCUMENT_MODEL,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Извлеки текст с чека/инвойса: позиции, суммы, валюта, дата, итого. Без пояснений.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(OPENROUTER_CHAT_URL, headers=headers, json=body)
        resp.raise_for_status()

    payload = resp.json()
    msg = (payload.get("choices") or [{}])[0].get("message", {})
    content = msg.get("content", "")

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        content = "\n".join([p for p in text_parts if p])

    return str(content).strip()


def _extract_text_from_pdf(file_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    chunks = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            chunks.append(t.strip())
    return "\n\n".join(chunks).strip()


async def _process_extracted_finance_text(update: Update, extracted_text: str, source: str, caption: str | None = None):
    if not extracted_text:
        await update.message.reply_text("😕 Не удалось распознать текст. Попробуй более чёткое фото/документ.")
        return

    preview = extracted_text if len(extracted_text) <= 350 else extracted_text[:350] + "…"
    await update.message.reply_text(f"📄 Распознал из {source}:\n{preview}")

    user_note = f"\nКомментарий пользователя: {caption}" if caption else ""
    prompt = (
        f"Пользователь отправил {source}. Ниже распознанный текст.{user_note}\n\n"
        f"{extracted_text}\n\n"
        "Извлеки транзакции и внеси их в учёт. Если данных мало, задай 1 короткий уточняющий вопрос."
    )
    await _reply_agent_stream(update, prompt)


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    photos = update.message.photo or []
    if not photos:
        await update.message.reply_text("❌ Фото не найдено.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    temp_path = None
    try:
        tg_file = await ctx.bot.get_file(photos[-1].file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            temp_path = tmp.name
        await tg_file.download_to_drive(custom_path=temp_path)

        with open(temp_path, "rb") as f:
            image_bytes = f.read()

        extracted = await _extract_text_from_image_bytes(image_bytes, "image/jpeg")
        await _process_extracted_finance_text(update, extracted, "фото чека", update.message.caption)
    except Exception as e:
        log.exception("Photo processing error: %s", e)
        await update.message.reply_text("❌ Не удалось обработать фото. Попробуй ещё раз.")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ Файл не найден.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    mime_type = doc.mime_type or "application/octet-stream"
    temp_suffix = ".pdf" if mime_type == "application/pdf" else ".bin"
    temp_path = None

    try:
        tg_file = await ctx.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=temp_suffix) as tmp:
            temp_path = tmp.name
        await tg_file.download_to_drive(custom_path=temp_path)

        if mime_type.startswith("image/"):
            with open(temp_path, "rb") as f:
                image_bytes = f.read()
            extracted = await _extract_text_from_image_bytes(image_bytes, mime_type)
            await _process_extracted_finance_text(update, extracted, "изображения", update.message.caption)
            return

        if mime_type == "application/pdf":
            extracted = _extract_text_from_pdf(temp_path)
            await _process_extracted_finance_text(update, extracted, "PDF-инвойса", update.message.caption)
            return

        await update.message.reply_text("⚠️ Пока поддерживаются только изображения и PDF-файлы.")
    except Exception as e:
        log.exception("Document processing error: %s", e)
        await update.message.reply_text("❌ Не удалось обработать файл. Попробуй другой PDF/изображение.")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    if not config.TRANSCRIBE_API_KEY:
        await update.message.reply_text(
            "🎤 Голосовые пока не настроены: добавь `TRANSCRIBE_API_KEY` в переменные окружения."
        )
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    temp_path = None
    try:
        voice = update.message.voice
        if not voice:
            await update.message.reply_text("❌ Не удалось получить голосовое сообщение.")
            return

        tg_file = await ctx.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            temp_path = tmp.name

        await tg_file.download_to_drive(custom_path=temp_path)
        text = ""
        if config.VOICE_DIRECT_MODE:
            try:
                text = await _transcribe_voice_direct(temp_path)
            except Exception as direct_error:
                log.warning("Direct voice mode failed, fallback to STT: %s", direct_error)

        if not text:
            text = await _transcribe_voice_file(temp_path)

        if not text:
            await update.message.reply_text("😕 Не смог распознать речь. Попробуй записать чуть громче/чётче.")
            return

        preview = text if len(text) <= 220 else text[:220] + "…"
        await update.message.reply_text(f"🎤 Распознал: {preview}")
        await _reply_agent_stream(update, text)
    except Exception as e:
        log.exception("Voice processing error: %s", e)
        await update.message.reply_text("❌ Ошибка при обработке голосового. Проверь ключ транскрибации и попробуй снова.")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not allowed(q.from_user.id):
        return
    await ctx.bot.send_chat_action(chat_id=q.message.chat_id, action="typing")
    prompts = {
        "dashboard": "Верни текущий дашборд",
        "plan":      "Сравни план с фактом за этот месяц",
        "stats":     "Дай подробную статистику за текущий месяц",
    }
    prompt = prompts.get(q.data, "Помоги")
    # Send placeholder, then stream
    placeholder = await q.message.reply_text("⏳ Генерирую...")
    import asyncio, time
    full_text = ""
    last_edit = 0.0
    try:
        async for chunk in agent.process_stream(prompt):
            full_text += chunk
            now = time.monotonic()
            if now - last_edit >= STREAM_EDIT_INTERVAL and full_text.strip():
                try:
                    await placeholder.edit_text(
                        md_to_html(full_text) + " ▍",
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    last_edit = now
                except Exception:
                    pass
    except Exception as e:
        log.exception("Stream error: %s", e)
        full_text = "❌ Ошибка при генерации ответа."
    try:
        await placeholder.edit_text(
            md_to_html(full_text) if full_text else "❌ Пустой ответ.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass

# ─── Helpers ───────────────────────────────────────────────────────────────────

async def _reply_agent_stream(update: Update, text: str):
    """Send a streaming response, gradually updating a placeholder message."""
    import time
    uid = update.effective_user.id
    hist = histories.get(uid, [])
    placeholder = await update.message.reply_text("⏳ Думаю...")
    full_text = ""
    last_edit = 0.0
    try:
        async for chunk in agent.process_stream(text, history=hist):
            full_text += chunk
            now = time.monotonic()
            if now - last_edit >= STREAM_EDIT_INTERVAL and full_text.strip():
                try:
                    await placeholder.edit_text(
                        md_to_html(full_text) + " ▍",
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    last_edit = now
                except Exception:
                    pass
    except Exception as e:
        log.exception("Agent stream error: %s", e)
        full_text = "❌ Ошибка. Попробуй ещё раз или напиши /start"
    # Final edit with full text, no cursor
    try:
        await placeholder.edit_text(
            md_to_html(full_text) if full_text else "❌ Пустой ответ.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    if full_text:
        hist.append({"role": "user",      "content": text})
        hist.append({"role": "assistant", "content": full_text})
        histories[uid] = hist[-20:]

# ─── Init & main ───────────────────────────────────────────────────────────────

async def post_init(app: Application):
    global agent
    log.info("Connecting to Google Sheets…")
    sheets.connect()
    
    agent = FinanceAgent(config.OPENROUTER_API_KEY, config.AI_MODEL, sheets, currency=config.CURRENCY)
    log.info("Agent initialized ✓")
    
    if app.job_queue:
        register_jobs(app.job_queue, config, app.bot, sheets, agent)
        log.info("Scheduler configured ✓")
        
    log.info("Bot ready ✓")

def _build_onboarding_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("plan",  cmd_plan),
        ],
        states={
            ONB_INCOME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_income)],
            ONB_RED:     [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_red)],
            ONB_YELLOW:  [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_yellow)],
            ONB_GREEN:   [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_green)],
        },
        fallbacks=[CommandHandler("cancel", onb_cancel)],
        allow_reentry=True,
    )

def main():
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(config.TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Onboarding ConversationHandler MUST come first
    app.add_handler(_build_onboarding_handler())
    
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("sheet", cmd_sheet))
    app.add_handler(CommandHandler("table", cmd_sheet))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    log.info("Starting polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
