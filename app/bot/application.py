"""Telegram bot application entry point."""

from app.bot.bootstrap import build_application, main, post_init

__all__ = ["build_application", "main", "post_init"]
