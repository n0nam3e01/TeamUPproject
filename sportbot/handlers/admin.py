"""
Команды организатора проекта: /stats и /export.

Работают только у того, чей telegram id записан в .env как ADMIN_ID.
Цифры отсюда идут в отчёт по социальному проекту.
"""

import csv
import html
import io
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

import database as db
import texts
from config import (
    ADMIN_ID,
    AUTO_BAN_DAYS,
    LONG_TIME_DAYS,
    MAX_BAN_DAYS,
    WARNINGS_BEFORE_BAN,
    now,
)
from scheduler import notify_players, safe_send

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


# ==========================================================
#   ПОМОЩНИКИ АДМИНКИ
# ==========================================================

def user_label(user) -> str:
    """
    Как показывать человека в админских списках: «Арман @arman (8Б)».
    Если ника нет — дописываем telegram id, чтобы к нему всё равно можно
    было обратиться командой.
    """
    name = html.escape(user["first_name"] or "Без имени")
    klass = f" ({user['grade']}{user['letter']})" if user["grade"] else ""

    if user["username"]:
        return f"{name} @{html.escape(user['username'])}{klass}"
    return f"{name}{klass} · id {user['user_id']}"


async def resolve_user(message: Message, query: str, example: str):
    """
    Находит человека по @нику или id. Если не вышло — сам объясняет,
    что не так, и возвращает None.
    """
    if not query:
        await message.answer(texts.ADMIN_NEED_USER.format(example=example))
        return None

    user = await db.find_user(query)
    if user is None:
        # Может быть, имён несколько — тогда объясним понятнее
        same_name = await db.count_users_by_name(query)
        if same_name > 1:
            await message.answer(texts.ADMIN_USER_AMBIGUOUS.format(
                name=html.escape(query.lstrip("@")), count=same_name))
        else:
            await message.answer(texts.ADMIN_USER_NOT_FOUND)
        return None
    return user


async def resolve_game(message: Message, query: str, example: str):
    """То же самое, но для номера игры."""
    number = (query or "").strip().lstrip("#")
    if not number.isdigit():
        await message.answer(texts.ADMIN_NEED_GAME.format(example=example))
        return None

    game = await db.get_game(int(number))
    if game is None or game["status"] == "deleted":
        await message.answer(texts.ADMIN_GAME_NOT_FOUND)
        return None
    return game


# ==========================================================
#   /admin — справка по командам организатора
# ==========================================================

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return
    await message.answer(texts.ADMIN_HELP)


# ==========================================================
#   /games — все игры с номерами
# ==========================================================

@router.message(Command("games"))
async def cmd_games(message: Message) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    games = await db.get_all_games_admin()
    if not games:
        await message.answer(texts.ADMIN_GAMES_EMPTY)
        return

    lines = [texts.ADMIN_GAMES_HEADER.format(count=len(games)), ""]
    for game in games:
        queue = f" +{game['waiting_count']}" if game["waiting_count"] else ""
        lines.append(
            f"<code>#{game['game_id']}</code> {texts.sport_emoji(game['sport'])} "
            f"{html.escape(game['sport'])} — "
            f"{texts.format_date_short(game['game_date'])} {game['game_time']} — "
            f"{game['players_count']}/{game['min_players']}{queue} — {game['status']}"
        )

    await message.answer("\n".join(lines))


# ==========================================================
#   /who — кто записан на игру
# ==========================================================

@router.message(Command("who"))
async def cmd_who(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    game = await resolve_game(message, command.args, "/who 12")
    if game is None:
        return

    game_id = game["game_id"]
    main = await db.get_players_full(game_id, "main")
    waiting = await db.get_players_full(game_id, "waiting")

    if not main and not waiting:
        await message.answer(texts.WHO_EMPTY)
        return

    lines = [texts.format_game_card(game), ""]

    if main:
        lines.append(texts.WHO_MAIN.format(count=len(main)))
        for number, player in enumerate(main, start=1):
            lines.append(f"{number}. {user_label(player)}")

    if waiting:
        lines.append("")
        lines.append(texts.WHO_WAITING.format(count=len(waiting)))
        for number, player in enumerate(waiting, start=1):
            lines.append(f"{number}. {user_label(player)}")

    await message.answer("\n".join(lines))


# ==========================================================
#   /delete_game — убрать игру
# ==========================================================

@router.message(Command("delete_game"))
async def cmd_delete_game(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    game = await resolve_game(message, command.args, "/delete_game 12")
    if game is None:
        return

    game_id = game["game_id"]

    # Сообщение собираем до удаления, пока данные игры ещё на месте
    text = texts.GAME_DELETED_FOR_PLAYERS.format(game=texts.format_game_card(game))
    sent = await notify_players(message.bot, game_id, text,
                                skip_user_id=message.from_user.id)

    await db.delete_game(game_id)
    logger.info("Организатор убрал игру #%s", game_id)

    await message.answer(texts.ADMIN_GAME_DELETED.format(game_id=game_id, sent=sent))


# ==========================================================
#   /users — список учеников
# ==========================================================

@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    users = await db.get_users_overview()
    if not users:
        await message.answer(texts.USERS_EMPTY)
        return

    lines = [texts.USERS_HEADER.format(count=len(users)), ""]
    current_class = None

    for user in users:
        klass = f"{user['grade']}{user['letter']}"
        if klass != current_class:
            lines.append(f"<b>{klass}</b>")
            current_class = klass

        warns = f" ⚠️{user['warnings_count']}" if user["warnings_count"] else ""

        # Показываем запрет, только если он ещё действует
        ban = user["banned_until"]
        active_ban = ban and ban > now().strftime("%Y-%m-%d %H:%M:%S")
        blocked = f" 🚫{texts.format_ban_until(ban)}" if active_ban else ""

        lines.append(
            f"  • {user_label(user)} — игр: {user['games_count']}, "
            f"{texts.format_last_played(user['last_played'])}{warns}{blocked}"
        )

    await message.answer("\n".join(lines))


# ==========================================================
#   /warn и /warns — предупреждения
# ==========================================================

@router.message(Command("warn"))
async def cmd_warn(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    # Первое слово — ник или id, всё остальное — причина
    parts = (command.args or "").split(maxsplit=1)
    user = await resolve_user(message, parts[0] if parts else "",
                              "/warn @alinur мат в названии игры")
    if user is None:
        return

    if len(parts) < 2 or not parts[1].strip():
        nick = user["username"] or user["user_id"]
        await message.answer(texts.ADMIN_NEED_REASON.format(nick=nick))
        return

    reason = parts[1].strip()
    total = await db.add_warning(user["user_id"], message.from_user.id, reason)

    delivered = await safe_send(
        message.bot, user["user_id"],
        texts.WARN_FOR_USER.format(reason=html.escape(reason)))

    logger.info("Организатор выдал предупреждение пользователю %s", user["user_id"])

    name = html.escape(user["first_name"] or "него")
    await message.answer(texts.WARN_SENT.format(name=name, count=total))
    if not delivered:
        await message.answer(texts.WARN_NOT_DELIVERED)

    # Набралось слишком много — закрываем создание игр автоматически
    if total >= WARNINGS_BEFORE_BAN and not await db.get_ban(user["user_id"]):
        stamp = await db.set_ban(user["user_id"], AUTO_BAN_DAYS)
        until = texts.format_ban_until(stamp)

        await safe_send(message.bot, user["user_id"], texts.BAN_AUTO_FOR_USER.format(
            until=until, count=total))
        logger.info("Автоблокировка создания игр для %s: %s предупреждений",
                    user["user_id"], total)
        await message.answer(texts.BAN_AUTO_NOTICE.format(
            name=name, count=total, until=until))


@router.message(Command("warns"))
async def cmd_warns(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    user = await resolve_user(message, (command.args or "").strip(), "/warns @alinur")
    if user is None:
        return

    name = html.escape(user["first_name"] or "него")
    warnings = await db.get_warnings(user["user_id"])

    if not warnings:
        await message.answer(texts.WARNS_EMPTY.format(name=name))
        return

    lines = [texts.WARNS_HEADER.format(name=name, count=len(warnings)), ""]
    for warning in warnings:
        when = warning["created_at"][:10] if warning["created_at"] else ""
        reason = html.escape(warning["reason"] or "")
        lines.append(f"• {when} — {reason}")

    await message.answer("\n".join(lines))


# ==========================================================
#   /clearwarns — стереть предупреждения
# ==========================================================

@router.message(Command("clearwarns"))
async def cmd_clearwarns(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    user = await resolve_user(message, (command.args or "").strip(),
                              "/clearwarns @alinur")
    if user is None:
        return

    name = html.escape(user["first_name"] or "него")
    count = await db.clear_warnings(user["user_id"])

    if not count:
        await message.answer(texts.WARNS_NOTHING_TO_CLEAR.format(name=name))
        return

    await safe_send(message.bot, user["user_id"], texts.WARNS_CLEARED_FOR_USER)
    logger.info("Организатор стёр предупреждения пользователю %s", user["user_id"])
    await message.answer(texts.WARNS_CLEARED.format(name=name, count=count))


# ==========================================================
#   /ban и /unban — создание игр
# ==========================================================

@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    # Первое слово — ник, второе — дни, остальное — причина
    parts = (command.args or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(texts.ADMIN_NEED_BAN_ARGS)
        return

    user = await resolve_user(message, parts[0], "/ban @alinur 7 причина")
    if user is None:
        return

    if not parts[1].isdigit() or not 1 <= int(parts[1]) <= MAX_BAN_DAYS:
        await message.answer(texts.ADMIN_BAD_BAN_DAYS.format(limit=MAX_BAN_DAYS))
        return

    days = int(parts[1])
    reason = parts[2].strip() if len(parts) > 2 else "без объяснения"

    stamp = await db.set_ban(user["user_id"], days)
    until = texts.format_ban_until(stamp)

    await safe_send(message.bot, user["user_id"], texts.BAN_FOR_USER.format(
        until=until, reason=html.escape(reason)))

    logger.info("Организатор закрыл создание игр пользователю %s на %s дней",
                user["user_id"], days)
    await message.answer(texts.BAN_SET.format(
        name=html.escape(user["first_name"] or "Он"), until=until))


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        await message.answer(texts.NOT_ADMIN)
        return

    user = await resolve_user(message, (command.args or "").strip(), "/unban @alinur")
    if user is None:
        return

    name = html.escape(user["first_name"] or "него")
    if not await db.clear_ban(user["user_id"]):
        await message.answer(texts.UNBAN_NOT_BANNED.format(name=name))
        return

    await safe_send(message.bot, user["user_id"], texts.UNBAN_FOR_USER)
    logger.info("Организатор снял запрет с пользователя %s", user["user_id"])
    await message.answer(texts.UNBAN_DONE.format(name=name))
