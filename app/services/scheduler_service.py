"""Scheduled tasks for the finance bot using JobQueue."""
import datetime
import logging

from telegram.ext import ContextTypes

from app.bot.handlers.callbacks import build_payment_reminder_text
from app.bot.keyboards import reminder_keyboard
from app.utils.markdown import md_to_html

log = logging.getLogger(__name__)


async def _broadcast_summary(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    config = context.job.data["config"]
    rendered = md_to_html(text)
    uids = config.ALLOWED_USERS if config.ALLOWED_USERS else []
    for uid in uids:
        await context.bot.send_message(chat_id=uid, text=rendered, parse_mode="HTML")

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    """Mini-summary of the day + advice if budget exceeded."""
    agent = context.job.data["agent"]
    
    prompt = "Проанализируй сегодняшний день (используй get_dashboard). Дай короткий вывод и 1 мотивационный финансовый совет (максимум 3 предложения)."
    try:
        text = await agent.process(prompt, is_job=True)
    except Exception as e:
        log.exception("Daily summary generation failed: %s", e)
        text = f"🌙 <b>Итоги дня</b>: Ошибка генерации ({e})"
    await _broadcast_summary(context, text)


async def weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Weekly report + AI analysis."""
    agent = context.job.data["agent"]
    
    prompt = "Подведи итоги прошедшей недели. Похвали за экономию или поругай за лишние 'Гулянки' (используй get_dashboard). Формат: короткий, красивый, с эмодзи."
    try:
        text = await agent.process(prompt, is_job=True)
    except Exception as e:
        log.exception("Weekly summary generation failed: %s", e)
        text = "📊 <b>Не удалось сгенерировать Итоги недели</b>"
    await _broadcast_summary(context, text)


async def monthly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Monthly report + Plan recommendations."""
    agent = context.job.data["agent"]
    
    prompt = (
        "Подведи глубокие итоги прошедшего месяца. ПРОАНАЛИЗИРУЙ данные (используй get_stats_by_month для прошлого и позапрошлого месяцев). "
        "Сравни траты по категориям, найди АНОМАЛИИ (резкий рост) и дай оценку выполнению Плана. "
        "Дай 2-3 жестких, но полезных совета по оптимизации бюджета на новый месяц."
    )
    try:
        text = await agent.process(prompt, is_job=True)
    except Exception as e:
        log.exception("Monthly summary generation failed: %s", e)
        text = "📅 <b>Не удалось сгенерировать Итоги месяца</b>"
    await _broadcast_summary(context, text)

async def monthly_onboarding(context: ContextTypes.DEFAULT_TYPE):
    """Sent on 1st of each month — invites user to fill in the new budget plan."""
    config = context.job.data['config']
    import datetime
    now = datetime.datetime.now()
    months = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    label = f"{months[now.month]} {now.year}"

    text = (
        f"🗓 <b>Новый месяц — {label}!</b>\n\n"
        "Пора заполнить план бюджета по зонам.\n"
        "Просто напиши <b>/plan</b> и я проведу тебя за 4 шага 🚀\n\n"
        "🔴 Красная зона — обязательные\n"
        "🟡 Жёлтая зона — гулянки\n"
        "🟢 Зелёная зона — разовые"
    )
    uids = config.ALLOWED_USERS if config.ALLOWED_USERS else []
    for uid in uids:
        await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")


async def expected_payment_reminders(context: ContextTypes.DEFAULT_TYPE):
    sheets = context.job.data["sheets"]
    config = context.job.data["config"]
    today = datetime.date.today()
    month = sheets.current_month_key(today)
    payments = sheets.list_expected_payments(active_only=True)
    uids = config.ALLOWED_USERS if config.ALLOWED_USERS else []

    for payment in payments:
        if not sheets.is_expected_payment_due(payment["due_day"], today):
            continue

        status = sheets.get_payment_status(payment["id"], month)
        if status["status"] == "paid":
            continue

        if status["last_reminded_at"] == today.isoformat():
            continue

        snooze_until = status.get("snooze_until", "")
        if snooze_until:
            try:
                if datetime.date.fromisoformat(snooze_until) > today:
                    continue
            except ValueError:
                pass

        text = md_to_html(build_payment_reminder_text(payment, month))
        markup = reminder_keyboard(payment["id"], month)
        for uid in uids:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML", reply_markup=markup)
        sheets.record_payment_reminder(payment["id"], month)


def register_jobs(job_queue, config, dp_bot, sheets_instance, agent_instance):
    import datetime
    import pytz
    tz = pytz.timezone(config.TIMEZONE)
    
    job_queue.run_daily(
        daily_summary,
        time=datetime.time(hour=21, minute=0, tzinfo=tz),
        data={'config': config, 'bot': dp_bot, 'sheets': sheets_instance, 'agent': agent_instance},
        name="daily_summary"
    )
    
    job_queue.run_daily(
        expected_payment_reminders,
        time=datetime.time(hour=9, minute=0, tzinfo=tz),
        data={'config': config, 'sheets': sheets_instance},
        name="expected_payment_reminders"
    )

    job_queue.run_daily(
        weekly_summary,
        time=datetime.time(hour=19, minute=0, tzinfo=tz),
        days=(6,),
        data={'config': config, 'sheets': sheets_instance, 'agent': agent_instance},
        name="weekly_summary"
    )
    
    # 1st of month at 09:00 — AI summary of last month
    job_queue.run_monthly(
        monthly_summary,
        when=datetime.time(hour=9, minute=0, tzinfo=tz),
        day=1,
        data={'config': config, 'sheets': sheets_instance, 'agent': agent_instance},
        name="monthly_summary"
    )
    
    # 1st of month at 09:05 — invite to fill new budget plan
    job_queue.run_monthly(
        monthly_onboarding,
        when=datetime.time(hour=9, minute=5, tzinfo=tz),
        day=1,
        data={'config': config},
        name="monthly_onboarding"
    )
