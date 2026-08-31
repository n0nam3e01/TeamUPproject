"""
Команды организатора проекта: /stats и /export.

Работают только у того, чей telegram id записан в .env как ADMIN_ID.
Цифры отсюда идут в отчёт по социальному проекту.
"""

import csv
import io
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

import database as db
import texts
from config import ADMIN_ID, LONG_TIME_DAYS, now

logger = logging.getLogger(__name__)
router = Router(name="admin")


def is_admin(message: Message) -> bool:
    """Проверяем, что команду прислал организатор проекта."""
    return message.from_user.id == ADMIN_ID and ADMIN_ID != 0


def rows_to_csv(headers: list[str], rows: list[list]) -> bytes:
    """
    Собирает CSV-файл в памяти.
    Кодировка utf-8-sig и разделитель ';' — чтобы русский текст нормально
    открывался и в Excel, и в Google Таблицах.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


# ==========================================================
#   /stats — цифры для отчёта
# ==========================================================

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    stats = await db.get_stats()
    inactive = await db.count_inactive_users(LONG_TIME_DAYS)

    # Распределение по классам: «8А — 12»
    if stats["grades"]:
        grades_block = "\n".join(
            f"   {row['grade']}{row['letter']} — {row['c']}"
            for row in stats["grades"]
        ) + "\n"
    else:
        grades_block = "   пока никого\n"

    # Средний размер команды: округляем до одного знака после запятой
    avg_team = f"{stats['avg_team']:.1f}" if stats["avg_team"] else "—"

    await message.answer(texts.STATS_TEMPLATE.format(
        users_total=stats["users_total"],
        grades_block=grades_block,
        games_total=stats["games_total"],
        games_done=stats["games_done"],
        games_cancelled=stats["games_cancelled"],
        unique_players=stats["unique_players"],
        avg_team=avg_team,
        top_sport=stats["top_sport"],
        cross_class=stats["cross_class"],
        inactive=inactive,
    ))

    logger.info("Организатор запросил статистику")


# ==========================================================
#   /export — выгрузка двух CSV-файлов
# ==========================================================

@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    games = await db.export_games()
    signups = await db.export_signups()

    if not games and not signups:
        await message.answer(texts.EXPORT_EMPTY)
        return

    # --- games.csv: все игры со всеми полями ---
    games_csv = rows_to_csv(
        headers=[
            "id игры", "id организатора", "вид спорта", "дата", "время",
            "место", "нужно игроков", "максимум игроков", "минут",
            "заметка", "статус",
            "уведомление о сборе", "напоминание отправлено", "создана",
        ],
        rows=[[
            game["game_id"], game["creator_id"], game["sport"],
            game["game_date"], game["game_time"], game["place"],
            game["min_players"], game["max_players"], game["duration_min"],
            game["note"], game["status"],
            game["notified_full"], game["notified_reminder"], game["created_at"],
        ] for game in games],
    )

    # --- signups.csv: кто на что записался, с именем и классом ---
    signups_csv = rows_to_csv(
        headers=[
            "id записи", "id игры", "вид спорта", "дата", "время", "статус игры",
            "состав", "id участника", "имя", "класс", "записался",
        ],
        rows=[[
            row["id"], row["game_id"], row["sport"],
            row["game_date"], row["game_time"], row["game_status"],
            "основной" if row["signup_status"] == "main" else "очередь",
            row["user_id"], row["first_name"],
            f"{row['grade']}{row['letter']}" if row["grade"] else "",
            row["created_at"],
        ] for row in signups],
    )

    caption = texts.EXPORT_CAPTION.format(date=now().strftime("%d.%m.%Y %H:%M"))

    await message.answer_document(
        BufferedInputFile(games_csv, filename="games.csv"),
        caption=caption,
    )
    await message.answer_document(
        BufferedInputFile(signups_csv, filename="signups.csv"),
    )

    logger.info("Организатор выгрузил данные: %s игр, %s записей",
                len(games), len(signups))
