"""
Вся работа с базой данных (файл data.db).

Три таблицы:
  users   — кто пользуется ботом (id, имя, ник, класс)
  games   — созданные игры
  signups — кто на какую игру записался

Каждая функция сама открывает и закрывает соединение с базой —
так проще и невозможно забыть его закрыть.
"""

from datetime import timedelta

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
    (SELECT COUNT(*) FROM signups s
     WHERE s.game_id = g.game_id AND s.status = 'main')    AS players_count,
    (SELECT COUNT(*) FROM signups s
     WHERE s.game_id = g.game_id AND s.status = 'waiting') AS waiting_count,
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
                max_players       INTEGER,
                duration_min      INTEGER NOT NULL DEFAULT 90,
                note              TEXT,
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
                status     TEXT NOT NULL DEFAULT 'main',
                created_at TEXT,
                UNIQUE(game_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                admin_id   INTEGER NOT NULL,
                reason     TEXT,
                created_at TEXT
            )
        """)
        await _add_missing_columns(db)
        await db.commit()


async def _add_missing_columns(db) -> None:
    """
    Дописывает новые колонки в базу, созданную предыдущей версией бота.
    Без этого старый data.db перестал бы открываться после обновления.
    """
    new_columns = {
        "games": {
            "max_players": "INTEGER",
            "duration_min": "INTEGER NOT NULL DEFAULT 90",
            "note": "TEXT",
        },
        "signups": {
            "status": "TEXT NOT NULL DEFAULT 'main'",
        },
    }

    for table, columns in new_columns.items():
        cursor = await db.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in await cursor.fetchall()}
        for name, kind in columns.items():
            if name not in existing:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


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
                      place: str, min_players: int, max_players=None,
                      duration_min: int = 90, note=None) -> int:
    """
    Создаёт игру и сразу записывает на неё организатора. Возвращает id новой игры.

    max_players — потолок состава; None означает «сколько угодно»
    duration_min — сколько минут длится игра
    note — необязательная заметка от организатора
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO games (creator_id, sport, game_date, game_time, place,
                               min_players, max_players, duration_min, note,
                               status, notified_full, notified_reminder, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 0, 0, ?)
        """, (creator_id, sport, game_date, game_time, place, min_players,
              max_players, duration_min, note, _stamp()))
        game_id = cursor.lastrowid

        # Организатор автоматически становится первым игроком основного состава
        await db.execute("""
            INSERT INTO signups (game_id, user_id, status, created_at)
            VALUES (?, ?, 'main', ?)
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

async def add_signup(game_id: int, user_id: int):
    """
    Записывает человека на игру.

    Возвращает:
      'main'    — попал в основной состав
      'waiting' — мест не было, встал в очередь
      None      — он уже был записан (спасает UNIQUE в таблице)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Есть ли потолок и не упёрлись ли мы в него
        cursor = await db.execute(
            "SELECT max_players FROM games WHERE game_id = ?", (game_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        max_players = row["max_players"]

        place = "main"
        if max_players:
            cursor = await db.execute(
                "SELECT COUNT(*) AS c FROM signups "
                "WHERE game_id = ? AND status = 'main'", (game_id,))
            if (await cursor.fetchone())["c"] >= max_players:
                place = "waiting"

        cursor = await db.execute("""
            INSERT OR IGNORE INTO signups (game_id, user_id, status, created_at)
            VALUES (?, ?, ?, ?)
        """, (game_id, user_id, place, _stamp()))
        await db.commit()

        return place if cursor.rowcount > 0 else None


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


async def get_players(game_id: int, status=None):
    """
    Telegram id тех, кто записан на игру — для рассылки уведомлений.
    status='main' — только основной состав, 'waiting' — только очередь,
    None — вообще все.
    """
    query = "SELECT user_id FROM signups WHERE game_id = ?"
    params = [game_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY id"

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        return [row[0] for row in await cursor.fetchall()]


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
            WHERE status NOT IN ('cancelled', 'deleted')
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
            WHERE g.status NOT IN ('cancelled', 'deleted')
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
                s.status AS signup_status,
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


# ==========================================================
#   ПРОФИЛЬ: ИЗМЕНЕНИЕ ДАННЫХ И ЛИЧНАЯ СТАТИСТИКА
# ==========================================================

async def update_user_class(user_id: int, grade: int, letter: str) -> None:
    """Меняет класс человека — например, когда он перешёл из 9-го в 10-й."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET grade = ?, letter = ? WHERE user_id = ?",
            (grade, letter, user_id),
        )
        await db.commit()


async def update_user_name(user_id: int, first_name: str) -> None:
    """Меняет имя, под которым человека видят в карточках игр."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET first_name = ? WHERE user_id = ?",
            (first_name, user_id),
        )
        await db.commit()


async def get_profile_stats(user_id: int) -> dict:
    """
    Личные цифры для экрана профиля: сколько игр создал, в скольких участвовал,
    какой спорт любимый и с ребятами из скольких классов уже играл.
    Отменённые игры нигде не считаются.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Сколько игр организовал
        cursor = await db.execute("""
            SELECT COUNT(*) AS c FROM games
            WHERE creator_id = ? AND status NOT IN ('cancelled', 'deleted')
        """, (user_id,))
        created = (await cursor.fetchone())["c"]

        # В скольких играх участвовал (включая свои)
        cursor = await db.execute("""
            SELECT COUNT(*) AS c
            FROM signups s
            JOIN games g ON g.game_id = s.game_id
            WHERE s.user_id = ? AND g.status NOT IN ('cancelled', 'deleted')
        """, (user_id,))
        joined = (await cursor.fetchone())["c"]

        # Любимый вид спорта — тот, в который записывался чаще всего
        cursor = await db.execute("""
            SELECT g.sport, COUNT(*) AS c
            FROM signups s
            JOIN games g ON g.game_id = s.game_id
            WHERE s.user_id = ? AND g.status NOT IN ('cancelled', 'deleted')
            GROUP BY g.sport
            ORDER BY c DESC
            LIMIT 1
        """, (user_id,))
        row = await cursor.fetchone()
        favourite = row["sport"] if row else None

        # Из скольких разных классов были ребята, с которыми он играл.
        # mine — его записи, others — записи остальных на те же игры.
        cursor = await db.execute("""
            SELECT DISTINCT u.grade, u.letter
            FROM signups mine
            JOIN signups others
                 ON others.game_id = mine.game_id AND others.user_id != mine.user_id
            JOIN games g ON g.game_id = mine.game_id
            JOIN users u ON u.user_id = others.user_id
            WHERE mine.user_id = ? AND g.status NOT IN ('cancelled', 'deleted')
        """, (user_id,))
        classes = {f"{r['grade']}{r['letter']}" for r in await cursor.fetchall()}

    return {
        "created": created,
        "joined": joined,
        "favourite": favourite,
        "classes_met": len(classes),
    }


async def get_players_full(game_id: int, status: str = "main"):
    """
    Кто записан на игру — с именами и классами, в порядке записи.
    status='main' — основной состав, 'waiting' — очередь.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT u.user_id, u.first_name, u.grade, u.letter
            FROM signups s
            LEFT JOIN users u ON u.user_id = s.user_id
            WHERE s.game_id = ? AND s.status = ?
            ORDER BY s.id
        """, (game_id, status))
        return [dict(row) for row in await cursor.fetchall()]


async def promote_from_waiting(game_id: int):
    """
    Поднимает первого из очереди в основной состав, если там освободилось место.
    Возвращает telegram id того, кого подняли, или None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT max_players FROM games WHERE game_id = ?", (game_id,))
        row = await cursor.fetchone()
        if row is None or not row["max_players"]:
            return None            # потолка нет — очереди быть не может

        cursor = await db.execute(
            "SELECT COUNT(*) AS c FROM signups "
            "WHERE game_id = ? AND status = 'main'", (game_id,))
        if (await cursor.fetchone())["c"] >= row["max_players"]:
            return None            # мест всё ещё нет

        # Берём того, кто встал в очередь раньше всех
        cursor = await db.execute(
            "SELECT id, user_id FROM signups "
            "WHERE game_id = ? AND status = 'waiting' ORDER BY id LIMIT 1",
            (game_id,))
        first = await cursor.fetchone()
        if first is None:
            return None            # очередь пуста

        await db.execute("UPDATE signups SET status = 'main' WHERE id = ?",
                         (first["id"],))
        await db.commit()
        return first["user_id"]


async def get_last_played(user_id: int):
    """
    Когда человек последний раз играл: дата вида '2026-08-18' или None.
    Считаются только игры, которые уже прошли и не были отменены.
    """
    moment = now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT MAX(g.game_date) AS last_date
            FROM signups s
            JOIN games g ON g.game_id = s.game_id
            WHERE s.user_id = ?
              AND s.status = 'main'
              AND g.status NOT IN ('cancelled', 'deleted')
              AND g.game_date || ' ' || g.game_time < ?
        """, (user_id, moment))
        row = await cursor.fetchone()
        return row[0] if row else None


async def count_inactive_users(days: int) -> int:
    """Сколько зарегистрированных ни разу не играли или не играли дольше days дней."""
    total = 0
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        user_ids = [row[0] for row in await cursor.fetchall()]

    threshold = (now() - timedelta(days=days)).date().isoformat()
    for user_id in user_ids:
        last = await get_last_played(user_id)
        if last is None or last < threshold:
            total += 1
    return total


# ==========================================================
#   АДМИНСКИЕ ФУНКЦИИ
# ==========================================================

async def find_user(query: str):
    """
    Ищет человека по @нику или по telegram id.
    Ник можно писать с собачкой и в любом регистре: @Alinur, alinur, ALINUR.
    Возвращает пользователя словарём или None.
    """
    cleaned = (query or "").strip().lstrip("@")
    if not cleaned:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Сначала пробуем как ник (регистр не важен)
        cursor = await db.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND username != ''",
            (cleaned,))
        row = await cursor.fetchone()
        if row:
            return dict(row)

        # Если это число — пробуем как telegram id
        if cleaned.isdigit():
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?", (int(cleaned),))
            row = await cursor.fetchone()
            if row:
                return dict(row)

        # Последняя попытка — по имени. Годится, только если такой один:
        # двух Дан различить невозможно, тогда пусть админ укажет ник или id.
        #
        # Сравниваем регистр в Python, а не в SQL: SQLite умеет приводить
        # к нижнему регистру только латиницу, и «Дана» с «дана» для него разные.
        cursor = await db.execute("SELECT * FROM users")
        matches = [
            dict(row) for row in await cursor.fetchall()
            if (row["first_name"] or "").lower() == cleaned.lower()
        ]
        if len(matches) == 1:
            return matches[0]

    return None


async def count_users_by_name(name: str) -> int:
    """Сколько человек с таким именем — чтобы объяснить админу неоднозначность."""
    wanted = (name or "").strip().lstrip("@").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT first_name FROM users")
        return sum(
            1 for row in await cursor.fetchall()
            if (row["first_name"] or "").lower() == wanted
        )


async def add_warning(user_id: int, admin_id: int, reason: str) -> int:
    """Записывает предупреждение и возвращает, сколько их теперь у человека всего."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO warnings (user_id, admin_id, reason, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, admin_id, reason, _stamp()))
        await db.commit()

        cursor = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE user_id = ?", (user_id,))
        return (await cursor.fetchone())[0]


async def count_warnings(user_id: int) -> int:
    """Сколько предупреждений у человека."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE user_id = ?", (user_id,))
        return (await cursor.fetchone())[0]


async def get_warnings(user_id: int):
    """Все предупреждения человека, свежие сверху."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT reason, created_at FROM warnings
            WHERE user_id = ? ORDER BY id DESC
        """, (user_id,))
        return [dict(row) for row in await cursor.fetchall()]


async def delete_game(game_id: int) -> bool:
    """
    Убирает игру из бота: статус становится 'deleted'.
    Сама строка остаётся в базе, чтобы отчёт по проекту не потерял историю,
    но нигде — ни в списках, ни в статистике — игра больше не появляется.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE games SET status = 'deleted' WHERE game_id = ? "
            "AND status != 'deleted'", (game_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_all_games_admin(limit: int = 30):
    """Все игры для админского списка — свежие сверху, включая прошедшие."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(GAME_SELECT + """
            WHERE g.status != 'deleted'
            ORDER BY g.game_date DESC, g.game_time DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in await cursor.fetchall()]


async def get_users_overview():
    """
    Сводка по всем пользователям для команды /users:
    кто это, из какого класса, сколько игр, когда играл, сколько предупреждений.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT
                u.user_id,
                u.username,
                u.first_name,
                u.grade,
                u.letter,
                (SELECT COUNT(*) FROM signups s
                 JOIN games g ON g.game_id = s.game_id
                 WHERE s.user_id = u.user_id
                   AND g.status NOT IN ('cancelled', 'deleted')) AS games_count,
                (SELECT COUNT(*) FROM warnings w
                 WHERE w.user_id = u.user_id) AS warnings_count
            FROM users u
            ORDER BY u.grade, u.letter, u.first_name
        """)
        users = [dict(row) for row in await cursor.fetchall()]

    # Дату последней игры считаем отдельной функцией — она уже есть выше
    for user in users:
        user["last_played"] = await get_last_played(user["user_id"])
    return users
