"""
Вся работа с базой данных (файл data.db).

Три таблицы:
  users   — кто пользуется ботом (id, имя, ник, класс)
  games   — созданные игры
  signups — кто на какую игру записался

Каждая функция сама открывает и закрывает соединение с базой —
так проще и невозможно забыть его закрыть.
"""

import aiosqlite

from config import DB_PATH, now


def _stamp() -> str:
    """Текущее время в виде строки — записываем его в поля created_at."""
    return now().strftime("%Y-%m-%d %H:%M:%S")


# Общий кусок SQL: берём игру + сколько человек записалось + кто организатор.
# Используется почти во всех запросах, поэтому вынесен отдельно.
GAME_SELECT = """
SELECT
    g.*,
    (SELECT COUNT(*) FROM signups s WHERE s.game_id = g.game_id) AS players_count,
    u.first_name AS creator_name,
    u.grade      AS creator_grade,
    u.letter     AS creator_letter
FROM games g
LEFT JOIN users u ON u.user_id = g.creator_id
"""

# Статусы, при которых игра ещё «живая»
ACTIVE_STATUSES = ("open", "full")


# ==========================================================
#   СОЗДАНИЕ ТАБЛИЦ
# ==========================================================

async def init_db() -> None:
    """Создаёт таблицы, если их ещё нет. Вызывается один раз при запуске бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                grade      INTEGER,
                letter     TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_id           INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id        INTEGER NOT NULL,
                sport             TEXT    NOT NULL,
                game_date         TEXT    NOT NULL,
                game_time         TEXT    NOT NULL,
                place             TEXT    NOT NULL,
                min_players       INTEGER NOT NULL,
                status            TEXT    NOT NULL DEFAULT 'open',
                notified_full     INTEGER NOT NULL DEFAULT 0,
                notified_reminder INTEGER NOT NULL DEFAULT 0,
                created_at        TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS signups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id    INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                created_at TEXT,
                UNIQUE(game_id, user_id)
            )
        """)
        await db.commit()


# ==========================================================
#   ПОЛЬЗОВАТЕЛИ
# ==========================================================

async def get_user(user_id: int):
    """Возвращает пользователя словарём или None, если он ещё не регистрировался."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def add_user(user_id: int, username: str, first_name: str,
                   grade: int, letter: str) -> None:
    """Сохраняет нового пользователя. Если он уже есть — обновляет имя, ник и класс."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, grade, letter, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                grade      = excluded.grade,
                letter     = excluded.letter
        """, (user_id, username, first_name, grade, letter, _stamp()))
        await db.commit()


# ==========================================================
#   ИГРЫ
# ==========================================================

async def create_game(creator_id: int, sport: str, game_date: str, game_time: str,
                      place: str, min_players: int) -> int:
    """Создаёт игру и сразу записывает на неё организатора. Возвращает id новой игры."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO games (creator_id, sport, game_date, game_time, place,
                               min_players, status, notified_full,
                               notified_reminder, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'open', 0, 0, ?)
        """, (creator_id, sport, game_date, game_time, place, min_players, _stamp()))
        game_id = cursor.lastrowid

        # Организатор автоматически становится первым игроком
        await db.execute("""
            INSERT INTO signups (game_id, user_id, created_at) VALUES (?, ?, ?)
        """, (game_id, creator_id, _stamp()))

        await db.commit()
        return game_id


async def get_game(game_id: int):
    """Одна игра со счётчиком игроков и данными организатора. None, если игры нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(GAME_SELECT + " WHERE g.game_id = ?", (game_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_upcoming_games(limit: int):
    """Ближайшие игры, которые ещё не начались. Сначала самые близкие."""
    moment = now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(GAME_SELECT + """
            WHERE g.status IN ('open', 'full')
              AND g.game_date || ' ' || g.game_time >= ?
            ORDER BY g.game_date, g.game_time
            LIMIT ?
        """, (moment, limit))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_games_created_by(user_id: int):
    """Активные игры, которые организует этот человек."""
    moment = now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(GAME_SELECT + """
            WHERE g.creator_id = ?
              AND g.status IN ('open', 'full')
              AND g.game_date || ' ' || g.game_time >= ?
            ORDER BY g.game_date, g.game_time
        """, (user_id, moment))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_games_joined_by(user_id: int):
    """
    Активные игры, куда человек записан.
    Свои игры сюда не попадают — они показываются в разделе «Ты организуешь».
    """
    moment = now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(GAME_SELECT + """
            WHERE g.status IN ('open', 'full')
              AND g.creator_id != ?
              AND g.game_date || ' ' || g.game_time >= ?
              AND EXISTS (SELECT 1 FROM signups s
                          WHERE s.game_id = g.game_id AND s.user_id = ?)
            ORDER BY g.game_date, g.game_time
        """, (user_id, moment, user_id))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def count_active_games(user_id: int) -> int:
    """Сколько активных игр человек уже создал (нужно для лимита в 3 штуки)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT COUNT(*) FROM games
            WHERE creator_id = ? AND status IN ('open', 'full')
        """, (user_id,))
        row = await cursor.fetchone()
        return row[0]


async def set_status(game_id: int, status: str) -> None:
    """Меняет статус игры: open / full / cancelled / done."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE games SET status = ? WHERE game_id = ?",
                         (status, game_id))
        await db.commit()


async def set_notified_full(game_id: int, value: int) -> None:
    """Отмечает, что сообщение «команда собрана» уже отправлено (или сбрасывает отметку)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE games SET notified_full = ? WHERE game_id = ?",
                         (value, game_id))
        await db.commit()


async def set_notified_reminder(game_id: int, value: int) -> None:
    """Отмечает, что напоминание за час уже отправлено."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE games SET notified_reminder = ? WHERE game_id = ?",
                         (value, game_id))
        await db.commit()


# ==========================================================
#   ЗАПИСЬ НА ИГРУ
# ==========================================================

async def add_signup(game_id: int, user_id: int) -> bool:
    """
    Записывает человека на игру.
    True — записали, False — он уже был записан (спасает UNIQUE в таблице).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT OR IGNORE INTO signups (game_id, user_id, created_at)
            VALUES (?, ?, ?)
        """, (game_id, user_id, _stamp()))
        await db.commit()
        return cursor.rowcount > 0


async def remove_signup(game_id: int, user_id: int) -> bool:
    """Убирает запись. True — отписали, False — его там и не было."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM signups WHERE game_id = ? AND user_id = ?",
            (game_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def is_signed_up(game_id: int, user_id: int) -> bool:
    """Записан ли человек на эту игру?"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM signups WHERE game_id = ? AND user_id = ?",
            (game_id, user_id),
        )
        return await cursor.fetchone() is not None


async def get_players(game_id: int):
    """Список telegram id всех, кто записан на игру — для рассылки уведомлений."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM signups WHERE game_id = ?", (game_id,)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


# ==========================================================
#   ФОНОВЫЕ ЗАДАЧИ (для scheduler.py)
# ==========================================================

async def get_games_waiting_reminder():
    """Активные игры, которым напоминание ещё не отправляли."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(GAME_SELECT + """
            WHERE g.status IN ('open', 'full')
              AND g.notified_reminder = 0
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def finish_past_games() -> int:
    """Переводит прошедшие игры в статус 'done'. Возвращает, сколько игр закрыли."""
    moment = now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE games SET status = 'done'
            WHERE status IN ('open', 'full')
              AND game_date || ' ' || game_time < ?
        """, (moment,))
        await db.commit()
        return cursor.rowcount


# ==========================================================
#   СТАТИСТИКА ДЛЯ /stats
# ==========================================================

async def get_stats() -> dict:
    """Собирает все цифры для отчёта по проекту."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Сколько всего пользователей
        cursor = await db.execute("SELECT COUNT(*) AS c FROM users")
        users_total = (await cursor.fetchone())["c"]

        # Распределение по классам: 8А — 12, 8Б — 9, ...
        cursor = await db.execute("""
            SELECT grade, letter, COUNT(*) AS c FROM users
            GROUP BY grade, letter
            ORDER BY grade, letter
        """)
        grades = [dict(row) for row in await cursor.fetchall()]

        # Игры: всего / состоялось / отменено
        cursor = await db.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'done'      THEN 1 ELSE 0 END) AS done,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled
            FROM games
        """)
        games = dict(await cursor.fetchone())

        # Сколько разных людей хоть раз записывались
        cursor = await db.execute("SELECT COUNT(DISTINCT user_id) AS c FROM signups")
        unique_players = (await cursor.fetchone())["c"]

        # Средний размер команды среди состоявшихся игр
        cursor = await db.execute("""
            SELECT AVG(cnt) AS avg_team FROM (
                SELECT COUNT(*) AS cnt
                FROM signups s
                JOIN games g ON g.game_id = s.game_id
                WHERE g.status = 'done'
                GROUP BY s.game_id
            )
        """)
        avg_team = (await cursor.fetchone())["avg_team"]

        # Самый популярный вид спорта
        cursor = await db.execute("""
            SELECT sport, COUNT(*) AS c FROM games
            WHERE status != 'cancelled'
            GROUP BY sport
            ORDER BY c DESC
            LIMIT 1
        """)
        top_row = await cursor.fetchone()
        top_sport = f"{top_row['sport']} ({top_row['c']})" if top_row else "—"

        # Главная метрика проекта: кто играл в одной игре с человеком из другого класса.
        # Берём все не отменённые игры и смотрим классы участников.
        cursor = await db.execute("""
            SELECT s.game_id, s.user_id, u.grade, u.letter
            FROM signups s
            JOIN games g ON g.game_id = s.game_id
            JOIN users u ON u.user_id = s.user_id
            WHERE g.status != 'cancelled'
        """)
        rows = [dict(row) for row in await cursor.fetchall()]

    # Группируем участников по играм: {game_id: [(user_id, '8Б'), ...]}
    by_game = {}
    for row in rows:
        klass = f"{row['grade']}{row['letter']}"
        by_game.setdefault(row["game_id"], []).append((row["user_id"], klass))

    # Для каждой игры проверяем: есть ли рядом кто-то из другого класса
    mixed_users = set()
    for players in by_game.values():
        classes = {klass for _, klass in players}
        if len(classes) > 1:            # в игре больше одного класса
            for user_id, klass in players:
                mixed_users.add(user_id)

    return {
        "users_total": users_total,
        "grades": grades,
        "games_total": games["total"] or 0,
        "games_done": games["done"] or 0,
        "games_cancelled": games["cancelled"] or 0,
        "unique_players": unique_players,
        "avg_team": avg_team,
        "top_sport": top_sport,
        "cross_class": len(mixed_users),
    }


# ==========================================================
#   ВЫГРУЗКА ДЛЯ /export
# ==========================================================

async def export_games():
    """Все игры со всеми полями — для файла games.csv."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM games ORDER BY game_id")
        return [dict(row) for row in await cursor.fetchall()]


async def export_signups():
    """Все записи вместе с именем и классом участника — для файла signups.csv."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT
                s.id,
                s.game_id,
                g.sport,
                g.game_date,
                g.game_time,
                g.status AS game_status,
                s.user_id,
                u.first_name,
                u.grade,
                u.letter,
                s.created_at
            FROM signups s
            LEFT JOIN games g ON g.game_id = s.game_id
            LEFT JOIN users u ON u.user_id = s.user_id
            ORDER BY s.id
        """)
        return [dict(row) for row in await cursor.fetchall()]
