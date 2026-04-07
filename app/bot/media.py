from __future__ import annotations

import base64
import os
import tempfile

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.state import allowed, is_english, log
from app.bot.streaming import reply_agent_stream
from app.core import config

OPENROUTER_TRANSCRIBE_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


async def transcribe_voice_file(file_path: str) -> str:
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


async def transcribe_voice_direct(file_path: str) -> str:
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
                        "input_audio": {"data": encoded, "format": "ogg"},
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


async def extract_text_from_image_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
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
                    {"type": "image_url", "image_url": {"url": data_url}},
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
    message = (payload.get("choices") or [{}])[0].get("message", {})
    content = message.get("content", "")

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        content = "\n".join(part for part in text_parts if part)

    return str(content).strip()


def extract_text_from_pdf(file_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks).strip()


async def process_extracted_finance_text(
    update: Update,
    extracted_text: str,
    source: str,
    caption: str | None = None,
) -> None:
    if not extracted_text:
        await update.message.reply_text(
            "😕 I could not extract any text. Please try a clearer image or document."
            if is_english()
            else "😕 Не удалось распознать текст. Попробуй более чёткое фото/документ."
        )
        return

    preview = extracted_text if len(extracted_text) <= 350 else extracted_text[:350] + "…"
    await update.message.reply_text(
        f"📄 Extracted from {source}:\n{preview}"
        if is_english()
        else f"📄 Распознал из {source}:\n{preview}"
    )

    if is_english():
        user_note = f"\nUser note: {caption}" if caption else ""
        prompt = (
            f"The user sent {source}. Below is the extracted text.{user_note}\n\n"
            f"{extracted_text}\n\n"
            "Extract the transactions and record them. If the data is insufficient, ask one short clarifying question."
        )
    else:
        user_note = f"\nКомментарий пользователя: {caption}" if caption else ""
        prompt = (
            f"Пользователь отправил {source}. Ниже распознанный текст.{user_note}\n\n"
            f"{extracted_text}\n\n"
            "Извлеки транзакции и внеси их в учёт. Если данных мало, задай 1 короткий уточняющий вопрос."
        )
    await reply_agent_stream(update, prompt)


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied." if is_english() else "⛔ Нет доступа.")
        return

    photos = update.message.photo or []
    if not photos:
        await update.message.reply_text("❌ Photo not found." if is_english() else "❌ Фото не найдено.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    temp_path = None
    try:
        tg_file = await ctx.bot.get_file(photos[-1].file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            temp_path = tmp.name
        await tg_file.download_to_drive(custom_path=temp_path)

        with open(temp_path, "rb") as file_obj:
            image_bytes = file_obj.read()

        extracted = await extract_text_from_image_bytes(image_bytes, "image/jpeg")
        await process_extracted_finance_text(update, extracted, "фото чека", update.message.caption)
    except Exception as exc:
        log.exception("Photo processing error: %s", exc)
        await update.message.reply_text(
            "❌ Failed to process the photo. Please try again."
            if is_english()
            else "❌ Не удалось обработать фото. Попробуй ещё раз."
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied." if is_english() else "⛔ Нет доступа.")
        return

    document = update.message.document
    if not document:
        await update.message.reply_text("❌ File not found." if is_english() else "❌ Файл не найден.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    mime_type = document.mime_type or "application/octet-stream"
    temp_suffix = ".pdf" if mime_type == "application/pdf" else ".bin"
    temp_path = None

    try:
        tg_file = await ctx.bot.get_file(document.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=temp_suffix) as tmp:
            temp_path = tmp.name
        await tg_file.download_to_drive(custom_path=temp_path)

        if mime_type.startswith("image/"):
            with open(temp_path, "rb") as file_obj:
                image_bytes = file_obj.read()
            extracted = await extract_text_from_image_bytes(image_bytes, mime_type)
            await process_extracted_finance_text(update, extracted, "изображения", update.message.caption)
            return

        if mime_type == "application/pdf":
            extracted = extract_text_from_pdf(temp_path)
            await process_extracted_finance_text(update, extracted, "PDF-инвойса", update.message.caption)
            return

        await update.message.reply_text(
            "⚠️ Only images and PDF files are supported for now."
            if is_english()
            else "⚠️ Пока поддерживаются только изображения и PDF-файлы."
        )
    except Exception as exc:
        log.exception("Document processing error: %s", exc)
        await update.message.reply_text(
            "❌ Failed to process the file. Please try another PDF or image."
            if is_english()
            else "❌ Не удалось обработать файл. Попробуй другой PDF/изображение."
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied." if is_english() else "⛔ Нет доступа.")
        return

    if not config.TRANSCRIBE_API_KEY:
        await update.message.reply_text(
            "🎤 Voice messages are not configured yet: add `TRANSCRIBE_API_KEY` to environment variables."
            if is_english()
            else "🎤 Голосовые пока не настроены: добавь `TRANSCRIBE_API_KEY` в переменные окружения."
        )
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    temp_path = None
    try:
        voice = update.message.voice
        if not voice:
            await update.message.reply_text(
                "❌ Failed to get the voice message."
                if is_english()
                else "❌ Не удалось получить голосовое сообщение."
            )
            return

        tg_file = await ctx.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            temp_path = tmp.name

        await tg_file.download_to_drive(custom_path=temp_path)
        text = ""
        if config.VOICE_DIRECT_MODE:
            try:
                text = await transcribe_voice_direct(temp_path)
            except Exception as exc:
                log.warning("Direct voice mode failed, fallback to STT: %s", exc)

        if not text:
            text = await transcribe_voice_file(temp_path)

        if not text:
            await update.message.reply_text(
                "😕 I could not recognize the speech. Please try speaking a bit louder or clearer."
                if is_english()
                else "😕 Не смог распознать речь. Попробуй записать чуть громче/чётче."
            )
            return

        preview = text if len(text) <= 220 else text[:220] + "…"
        await update.message.reply_text(
            f"🎤 Transcribed: {preview}" if is_english() else f"🎤 Распознал: {preview}"
        )
        await reply_agent_stream(update, text)
    except Exception as exc:
        log.exception("Voice processing error: %s", exc)
        await update.message.reply_text(
            "❌ Error while processing the voice message. Check the transcription key and try again."
            if is_english()
            else "❌ Ошибка при обработке голосового. Проверь ключ транскрибации и попробуй снова."
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
