"""Scheduled tasks for the finance bot using JobQueue."""
from telegram.ext import ContextTypes
import datetime

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    """Mini-summary of the day + advice if budget exceeded."""
    config = context.job.data['config']
    agent = context.job.data['agent']
    sheets = context.job.data['sheets']
    
    prompt = "Проанализируй сегодняшний день (используй get_dashboard). Дай короткий вывод и 1 мотивационный финансовый совет (максимум 3 предложения)."
    try:
        text = await agent.process(prompt, is_job=True)
    except Exception as e:
        text = f"🌙 <b>Итоги дня</b>: Ошибка генерации ({e})"
    
    # If ALLOWED_USERS is empty, we don't know who to send to unless we track them. 
    # For now, we assume ALLOWED_USERS has the admin IDs if they want scheduled jobs.
    uids = config.ALLOWED_USERS if config.ALLOWED_USERS else []
    for uid in uids:
        await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")


async def weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Weekly report + AI analysis."""
    config = context.job.data['config']
    agent = context.job.data['agent']
    
    prompt = "Подведи итоги прошедшей недели. Похвали за экономию или поругай за лишние 'Гулянки' (используй get_dashboard). Формат: короткий, красивый, с эмодзи."
    try:
        text = await agent.process(prompt, is_job=True)
    except:
        text = "📊 <b>Не удалось сгенерировать Итоги недели</b>"
        
    uids = config.ALLOWED_USERS if config.ALLOWED_USERS else []
    for uid in uids:
        await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")


async def monthly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Monthly report + Plan recommendations."""
    config = context.job.data['config']
    agent = context.job.data['agent']
    
    prompt = "Подведи итоги прошедшего месяца (используй get_dashboard). Дай оценку выполнению Плана и посоветуй, как скорректировать бюджет на следующий месяц."
    try:
        text = await agent.process(prompt, is_job=True)
    except:
        text = "📅 <b>Не удалось сгенерировать Итоги месяца</b>"
        
    uids = config.ALLOWED_USERS if config.ALLOWED_USERS else []
    for uid in uids:
        await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")

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
