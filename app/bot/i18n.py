from __future__ import annotations

def current_language() -> str:
    return "en"


def is_russian() -> bool:
    return False


async def localize(english_text: str, russian_text: str | None = None) -> str:
    return english_text
