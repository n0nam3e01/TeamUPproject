"""
Точка входа. Запуск: python bot.py

Что тут происходит по шагам:
  1. включаем логи (что бот делает — видно в консоли)
  2. проверяем, что токен на месте
  3. создаём таблицы в базе, если их ещё нет
  4. подключаем все роутеры (обработчики кнопок и команд)
  5. запускаем планировщик напоминаний
  6. запускаем самого бота и ждём сообщений

Остановить бота — Ctrl + C в окне консоли.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from config import BOT_NAME, BOT_TOKEN
from handlers import routers
from scheduler import setup_scheduler

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Настраиваем, как выглядят сообщения в консоли."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Планировщик слишком болтливый — оставляем от него только важное
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()

    if not BOT_TOKEN:
        logger.error(
            "Не найден BOT_TOKEN. Создай рядом с bot.py файл .env "
            "и впиши в него токен от @BotFather (образец — в .env.example)."
        )
        return

    # Таблицы создаются один раз и потом просто открываются
    await db.init_db()
    logger.info("База данных готова")

    # parse_mode=HTML нужен, чтобы работали <b>жирный</b> и <i>курсив</i> в текстах
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Сразу здороваемся с Telegram — так сломанный токен видно до запуска всего остального
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        logger.error(
            "Telegram не принял этот BOT_TOKEN. Проверь, что в .env скопирован "
            "весь токен целиком, без пробелов и кавычек."
        )
        await bot.session.close()
        return
    except TelegramNetworkError:
        logger.error("Нет связи с Telegram. Проверь интернет и попробуй снова.")
        await bot.session.close()
        return

    dispatcher = Dispatcher(storage=MemoryStorage())

    for router in routers:
        dispatcher.include_router(router)
    logger.info("Подключено роутеров: %s", len(routers))

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Планировщик запущен: напоминания и закрытие прошедших игр")

    logger.info("Бот «%s» (@%s) запущен. Останов — Ctrl+C", BOT_NAME, me.username)

    try:
        # Сбрасываем сообщения, пришедшие пока бот был выключен
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\nБот остановлен вручную")
