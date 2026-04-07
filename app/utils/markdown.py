from __future__ import annotations

import html as htmllib
import re


def md_to_html(text: str) -> str:
    """Convert AI markdown output into Telegram-safe HTML."""
    parts = re.split(r'(```[\s\S]*?```|`[^`]+`)', text)
    result: list[str] = []

    for part in parts:
        if part.startswith('```'):
            inner = re.sub(r'^```\w*\n?', '', part)
            inner = re.sub(r'\n?```$', '', inner)
            result.append(f'<pre><code>{htmllib.escape(inner)}</code></pre>')
            continue

        if part.startswith('`') and part.endswith('`') and len(part) > 2:
            result.append(f'<code>{htmllib.escape(part[1:-1])}</code>')
            continue

        escaped = htmllib.escape(part)
        escaped = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', escaped, flags=re.MULTILINE)
        escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
        escaped = re.sub(r'__(.+?)__', r'<b>\1</b>', escaped)
        escaped = re.sub(r'(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)', r'<i>\1</i>', escaped)
        escaped = re.sub(r'(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)', r'<i>\1</i>', escaped)
        escaped = re.sub(r'~~(.+?)~~', r'<s>\1</s>', escaped)
        escaped = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escaped)

        def fmt_table(match: re.Match[str]) -> str:
            lines = [line.strip() for line in match.group(0).strip().splitlines() if line.strip()]
            rows: list[str] = []
            for line in lines:
                if re.match(r'^[\|\s\-:]+$', line):
                    continue
                cells = [cell.strip() for cell in line.strip('|').split('|')]
                rows.append('  '.join(f'{cell:<14}' for cell in cells))
            return '<pre>' + '\n'.join(rows) + '</pre>'

        escaped = re.sub(r'((?:^\|.+\|\s*\n?)+)', fmt_table, escaped, flags=re.MULTILINE)
        escaped = re.sub(r'^[-*_]{3,}$', '─────────────────', escaped, flags=re.MULTILINE)
        result.append(escaped)

    return ''.join(result)
