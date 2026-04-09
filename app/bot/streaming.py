from __future__ import annotations

import os
import re
import time

from telegram import Update

from app.bot.state import STREAM_EDIT_INTERVAL, get_agent, histories, is_english, log
from app.utils.markdown import md_to_html


async def stream_text_reply(message, stream, *, empty_text: str, error_text: str) -> str:
    placeholder_text = "⏳ Thinking..." if is_english() else "⏳ Думаю..."
    placeholder = await message.reply_text(placeholder_text)
    full_text = ""
    last_edit = 0.0

    try:
        async for chunk in stream:
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
    except Exception as exc:
        log.exception("Streaming response error: %s", exc)
        full_text = error_text

    images = []
    clean_text = full_text
    
    # Extract Markdown image tags with /tmp/ path
    for match in re.finditer(r'!\[.*?\]\((/tmp/.*?\.png)\)', full_text):
        path = match.group(1)
        if os.path.exists(path):
            images.append(path)
            
    # Clean the text
    clean_text = re.sub(r'!\[.*?\]\((/tmp/.*?\.png)\)', '', clean_text).strip()

    try:
        await placeholder.edit_text(
            md_to_html(clean_text) if clean_text else empty_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass
        
    for path in set(images):
        try:
            with open(path, 'rb') as f:
                await placeholder.reply_photo(photo=f)
        except Exception as e:
            log.exception("Failed to send chart photo: %s", e)

    return clean_text


async def reply_agent_stream(update: Update, text: str) -> None:
    uid = update.effective_user.id
    history = histories.get(uid, [])
    final_text = await stream_text_reply(
        update.message,
        get_agent().process_stream(text, history=history),
        empty_text="❌ Empty response." if is_english() else "❌ Пустой ответ.",
        error_text=(
            "❌ Error. Please try again or send /start"
            if is_english()
            else "❌ Ошибка. Попробуй ещё раз или напиши /start"
        ),
    )
    if final_text:
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": final_text})
        histories[uid] = history[-20:]
