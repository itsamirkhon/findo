from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ConversationHandler, ContextTypes, MessageHandler, filters

from app.bot.keyboards import main_keyboard
from app.bot.state import (
    ONB_GREEN,
    ONB_INCOME,
    ONB_RED,
    ONB_YELLOW,
    allowed,
    current_month,
    is_english,
    month_label,
    sheets,
)
from app.services.sheets_service import RED_ZONE_CATEGORIES


async def send_welcome(update: Update) -> None:
    if is_english():
        text = (
            "👋 *Findo — Finance AI Assistant*\n\n"
            "Use the buttons below to open settings or your table."
        )
    else:
        text = (
            "👋 *Findo — Финансовый ИИ-ассистент*\n\n"
            "Используй кнопки ниже, чтобы открыть настройки или таблицу."
        )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied." if is_english() else "⛔ Нет доступа.")
        return ConversationHandler.END

    month = current_month()
    if not sheets.has_budget_for_month(month):
        if is_english():
            await update.message.reply_text(
                f"🗓 *Budget setup for {month}*\n\n"
                "No budget plan is set for this month yet. Let's configure it.\n\n"
                "👉 *Step 1/4:* What is your expected income this month? (EUR)",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"🗓 *Настройка бюджета на {month_label()}*\n\n"
                "Для тебя ещё не заполнен план на этот месяц. Давай настроим!\n\n"
                "👉 *Шаг 1/4:* Какой ожидаемый доход в этом месяце? (EUR)",
                parse_mode="Markdown",
            )
        return ONB_INCOME

    await send_welcome(update)
    return ConversationHandler.END


async def cmd_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        return ConversationHandler.END
    if is_english():
        await update.message.reply_text(
            f"🗓 *Budget setup for {current_month()}*\n\n"
            "Step 1/4: What is your expected income this month? (EUR)",
            parse_mode="Markdown",
        )
        return ONB_INCOME
    await update.message.reply_text(
        f"🗓 *Настройка бюджета на {month_label()}*\n\n"
        "Шаг 1/4: Какой ожидаемый доход в этом месяце? (EUR)",
        parse_mode="Markdown",
    )
    return ONB_INCOME


async def onb_income(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["onb_income"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a number. Example: `2000`"
            if is_english()
            else "❌ Пожалуйста, введи число. Например: `2000`",
            parse_mode="Markdown",
        )
        return ONB_INCOME

    categories = ", ".join(RED_ZONE_CATEGORIES)
    if is_english():
        await update.message.reply_text(
            f"✅ Income: {ctx.user_data['onb_income']}€\n\n"
            "👉 *Step 2/4:* Red zone limits 🔴\n"
            f"Categories: `{categories}`\n\n"
            "Enter amounts separated by commas in the same order:\n"
            "Example: `467, 50, 17, 11, 30, 100, 20`",
            parse_mode="Markdown",
        )
        return ONB_RED
    await update.message.reply_text(
        f"✅ Доход: {ctx.user_data['onb_income']}€\n\n"
        "👉 *Шаг 2/4:* Лимиты Красной зоны 🔴\n"
        f"Категории: `{categories}`\n\n"
        "Введи суммы через запятую (в том же порядке):\n"
        "Пример: `467, 50, 17, 11, 30, 100, 20`",
        parse_mode="Markdown",
    )
    return ONB_RED


async def onb_red(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        values = [float(value.strip()) for value in update.message.text.split(",")]
        if len(values) != len(RED_ZONE_CATEGORIES):
            raise ValueError
        ctx.user_data["onb_red"] = dict(zip(RED_ZONE_CATEGORIES, values))
    except (ValueError, IndexError):
        await update.message.reply_text(
            (
                f"❌ You need {len(RED_ZONE_CATEGORIES)} numbers separated by commas. "
                "Example: `467, 50, 17, 11, 30, 100, 20`"
            )
            if is_english()
            else f"❌ Нужно {len(RED_ZONE_CATEGORIES)} чисел через запятую. Пример: `467, 50, 17, 11, 30, 100, 20`",
            parse_mode="Markdown",
        )
        return ONB_RED

    total_red = sum(ctx.user_data["onb_red"].values())
    if is_english():
        await update.message.reply_text(
            f"✅ Red zone: {total_red}€\n\n"
            "👉 *Step 3/4:* Yellow zone limit 🟡 (restaurants / fun)?\n"
            "Example: `150`",
            parse_mode="Markdown",
        )
        return ONB_YELLOW
    await update.message.reply_text(
        f"✅ Красная зона: {total_red}€\n\n"
        "👉 *Шаг 3/4:* Лимит Жёлтой зоны 🟡 (Гулянки/рестораны)?\n"
        "Пример: `150`",
        parse_mode="Markdown",
    )
    return ONB_YELLOW


async def onb_yellow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["onb_yellow"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text(
            "❌ Enter a number. Example: `150`"
            if is_english()
            else "❌ Введи число. Например: `150`",
            parse_mode="Markdown",
        )
        return ONB_YELLOW

    if is_english():
        await update.message.reply_text(
            f"✅ Yellow zone: {ctx.user_data['onb_yellow']}€\n\n"
            "👉 *Step 4/4:* Green zone limit 🟢 (one-time purchases)?\n"
            "Example: `200`",
            parse_mode="Markdown",
        )
        return ONB_GREEN
    await update.message.reply_text(
        f"✅ Жёлтая зона: {ctx.user_data['onb_yellow']}€\n\n"
        "👉 *Шаг 4/4:* Лимит Зелёной зоны 🟢 (Разовые покупки)?\n"
        "Пример: `200`",
        parse_mode="Markdown",
    )
    return ONB_GREEN


async def onb_green(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["onb_green"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text(
            "❌ Enter a number. Example: `200`"
            if is_english()
            else "❌ Введи число. Например: `200`",
            parse_mode="Markdown",
        )
        return ONB_GREEN

    month = current_month()
    try:
        sheets.set_budget_plan(
            month=month,
            income=ctx.user_data["onb_income"],
            red_limits=ctx.user_data["onb_red"],
            yellow_limit=ctx.user_data["onb_yellow"],
            green_limit=ctx.user_data["onb_green"],
        )
        if is_english():
            await update.message.reply_text(
                f"🎉 *Budget for {month} saved!*\n\n"
                f"🔴 Red: {sum(ctx.user_data['onb_red'].values()):.0f}€\n"
                f"🟡 Yellow: {ctx.user_data['onb_yellow']:.0f}€\n"
                f"🟢 Green: {ctx.user_data['onb_green']:.0f}€\n"
                f"💰 Planned income: {ctx.user_data['onb_income']:.0f}€\n\n"
                "We are ready. Send expenses in plain English.",
                parse_mode="Markdown",
                reply_markup=main_keyboard(),
            )
            return ConversationHandler.END
        await update.message.reply_text(
            f"🎉 *План на {month_label()} записан!*\n\n"
            f"🔴 Красная: {sum(ctx.user_data['onb_red'].values()):.0f}€\n"
            f"🟡 Жёлтая: {ctx.user_data['onb_yellow']:.0f}€\n"
            f"🟢 Зелёная: {ctx.user_data['onb_green']:.0f}€\n"
            f"💰 Доход (план): {ctx.user_data['onb_income']:.0f}€\n\n"
            "Начинаем учёт! Вводи расходы в свободной форме 💬",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
    except Exception as exc:
        await update.message.reply_text(
            f"❌ Error while saving the budget plan: {exc}"
            if is_english()
            else f"❌ Ошибка записи плана: {exc}"
        )
    return ConversationHandler.END


async def onb_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Setup cancelled." if is_english() else "❌ Настройка отменена.",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("plan", cmd_plan),
        ],
        states={
            ONB_INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_income)],
            ONB_RED: [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_red)],
            ONB_YELLOW: [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_yellow)],
            ONB_GREEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, onb_green)],
        },
        fallbacks=[CommandHandler("cancel", onb_cancel)],
        allow_reentry=True,
    )
