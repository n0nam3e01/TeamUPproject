"""
Фоновые задачи бота — работают сами, без участия пользователя.

  Каждые 5 минут — проверяем, каким играм пора отправить напоминание за час.
  Каждый час    — прошедшие игры закрываем и просим участников
                  оценить, как всё прошло.

Здесь же лежат две функции безопасной отправки сообщений (safe_send и
notify_players). Они нужны и напоминаниям, и хендлерам: если человек
заблокировал бота, рассылка не должна падать целиком.
"""

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
import keyboards as kb
import texts
from config import (
    REMINDER_MAX_MINUTES,
    REMINDER_MIN_MINUTES,
    TZ,
    game_datetime,
    now,
)

logger = logging.getLogger(__name__)


# ==========================================================
#   БЕЗОПАСНАЯ ОТПРАВКА
# ==========================================================

async def safe_send(bot: Bot, user_id: int, text: str) -> bool:
    """
    Отправляет сообщение одному человеку.
    Если он заблокировал бота или удалил чат — просто пишем это в лог
    и идём дальше, чтобы не сломать всю рассылку.
    """
    try:
        await bot.send_message(user_id, text)
        return True
    except Exception as error:
        logger.warning("Не смог написать пользователю %s: %s", user_id, error)
        return False


async def notify_players(bot: Bot, game_id: int, text: str,
                         skip_user_id: int | None = None,
                         status: str | None = None) -> int:
    """
    Рассылает сообщение тем, кто записан на игру.

    skip_user_id — кого пропустить (например, самого организатора)
    status — 'main' только основному составу, None (по умолчанию) — вообще всем,
             включая очередь: отмену игры должны узнать и они

    Возвращает, скольким удалось написать.
    """
    sent = 0
    for user_id in await db.get_players(game_id, status):
        if user_id == skip_user_id:
            continue
        if await safe_send(bot, user_id, text):
            sent += 1
    return sent


# ==========================================================
#   ЗАДАЧА 1: НАПОМИНАНИЯ ЗА ЧАС
# ==========================================================

async def check_reminders(bot: Bot) -> None:
    """
    Ищет игры, до начала которых осталось около часа, и рассылает напоминание.
    Флаг notified_reminder не даёт отправить его дважды.
    """
    moment = now()

    for game in await db.get_games_waiting_reminder():
        minutes_left = (game_datetime(game) - moment).total_seconds() / 60

        if not REMINDER_MIN_MINUTES <= minutes_left <= REMINDER_MAX_MINUTES:
            continue

        text = texts.REMINDER.format(
            game=texts.format_game_short(game),
            count=game["players_count"],
        )
        sent = await notify_players(bot, game["game_id"], text, status="main")
        await db.set_notified_reminder(game["game_id"], 1)

        logger.info(
            "Напоминание по игре #%s (%s) отправлено %s игрокам",
            game["game_id"], game["sport"], sent,
        )


# ==========================================================
#   ЗАДАЧА 2: ЗАКРЫТИЕ ПРОШЕДШИХ ИГР
# ==========================================================

async def close_past_games(bot: Bot) -> None:
    """
    Игры, время которых уже прошло, переводим в статус 'done'
    и сразу спрашиваем у участников, как всё прошло.
    """
    closed = await db.finish_past_games()
    if closed:
        logger.info("Закрыто прошедших игр: %s", closed)

    await ask_for_reviews(bot)


async def ask_for_reviews(bot: Bot) -> None:
    """
    Просит участников оценить недавно прошедшую игру.
    Флаг review_asked не даёт спросить дважды, а про старые игры
    не спрашиваем вовсе — это делает сам запрос в базе.
    """
    for game in await db.get_games_for_review():
        game_id = game["game_id"]
        text = texts.REVIEW_ASK.format(game=texts.format_game_short(game))

        asked = 0
        for user_id in await db.get_players(game_id, "main"):
            try:
                await bot.send_message(
                    user_id, text, reply_markup=kb.review_stars_kb(game_id))
                asked += 1
            except Exception as error:
                logger.warning("Не смог спросить отзыв у %s: %s", user_id, error)

        await db.set_review_asked(game_id)
        logger.info("Спросил отзыв об игре #%s у %s участников", game_id, asked)


# ==========================================================
#   ЗАПУСК ПЛАНИРОВЩИКА
# ==========================================================

def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создаёт планировщик и вешает на него обе задачи. Запускает bot.py."""
    scheduler = AsyncIOScheduler(timezone=TZ)

    scheduler.add_job(
        check_reminders,
        trigger="interval",
        minutes=5,
        args=[bot],
        id="reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        close_past_games,
        trigger="interval",
        hours=1,
        args=[bot],
        id="close_games",
        replace_existing=True,
    )

    return scheduler
