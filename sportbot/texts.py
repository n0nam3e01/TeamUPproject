"""
ВСЕ тексты бота в одном месте.

Хочешь поменять формулировку — меняй здесь, в остальные файлы лезть не надо.
Внизу файла — три помощника, которые красиво собирают дату и карточку игры.
"""

import html
from datetime import datetime, timedelta

from config import (
    BOT_NAME,
    DEFAULT_DURATION,
    DURATIONS,
    CUSTOM_TEXT_MAX_LEN,
    DEFAULT_SPORT_EMOJI,
    MIN_PLAYERS_HIGH,
    MIN_PLAYERS_LOW,
    SPORT_EMOJI,
    now,
)

# ==========================================================
#   НАДПИСИ НА КНОПКАХ
# ==========================================================

BTN_CREATE = "🏀 Создать игру"
BTN_LIST = "📋 Список игр"
BTN_MY = "🗓 Мои игры"
BTN_PROFILE = "👤 Профиль"
BTN_HELP = "❓ Помощь"

BTN_CANCEL = "⬅️ Отмена"
BTN_OTHER = "Другое"

BTN_TODAY = "Сегодня"
BTN_TOMORROW = "Завтра"
BTN_AFTER_TOMORROW = "Послезавтра"
BTN_OTHER_DATE = "Другая дата"

BTN_CONFIRM_YES = "✅ Создать"
BTN_CONFIRM_NO = "❌ Отмена"

BTN_SIGNUP = "✅ Записаться"
BTN_SIGNOUT = "❌ Отписаться"
BTN_CANCEL_GAME = "🗑 Отменить игру"
BTN_CANCEL_GAME_YES = "Да, отменить"
BTN_CANCEL_GAME_NO = "Нет, оставить"
BTN_CREATE_FIRST = "🏀 Создать игру"
BTN_SHARE = "🔗 Позвать ребят"
BTN_NO_LIMIT = "Без ограничения"
BTN_SKIP = "Пропустить"
BTN_EDIT_CLASS = "✏️ Изменить класс"
BTN_EDIT_NAME = "✏️ Изменить имя"
BTN_PROFILE_BACK = "⬅️ Назад к профилю"


# ==========================================================
#   ЗНАКОМСТВО И МЕНЮ
# ==========================================================

WELCOME = (
    f"Привет! Я {BOT_NAME} 👋\n\n"
    "Помогаю нашей школе собираться на игры после уроков: "
    "кто-то создаёт игру, остальные записываются одной кнопкой.\n\n"
    "Давай познакомимся."
)

ASK_GRADE = "В каком ты классе? Выбери параллель 👇"
ASK_LETTER = "А буква какая? Если твоей нет на кнопках — нажми «Другое»"
BAD_GRADE = "Нажми, пожалуйста, кнопку с номером класса 👇"
BAD_LETTER = "Нажми кнопку с буквой класса или напиши свою одной буквой 👇"
ASK_CUSTOM_LETTER = "Напиши букву своего класса — ровно один символ, например Е"
BAD_CUSTOM_LETTER = (
    "Нужен ровно один символ, и это должна быть буква.\n"
    "Например: Е или Ж. Попробуй ещё раз:"
)

REG_DONE = "Отлично, {name} ({grade}{letter})! Теперь ты в деле 🔥"

MENU = "Что делаем?"
MENU_BACK = "Ты в главном меню 👇"

NEED_START = "Мы ещё не знакомы. Отправь /start, это займёт 5 секунд."
UNKNOWN = "Не понял 🤔 Нажми кнопку в меню или отправь /start"

HELP = (
    f"<b>{BOT_NAME} — как этим пользоваться</b>\n\n"
    "🏀 <b>Создать игру</b> — выбираешь спорт, день, время, место и сколько нужно "
    "человек. Игра появится в общем списке, и ты автоматически записан первым.\n\n"
    "📋 <b>Список игр</b> — все ближайшие игры. Под каждой кнопка «Записаться». "
    "Передумал — жмёшь «Отписаться».\n\n"
    "🗓 <b>Мои игры</b> — что ты организуешь и куда записан. "
    "Свою игру можно отменить.\n\n"
    "👤 <b>Профиль</b> — твоё имя, класс и личная статистика. "
    "Перешёл в другой класс или хочешь, чтобы тебя записывали иначе — меняешь прямо там.\n\n"
    "Когда народу набралось сколько нужно — всем придёт «Команда собрана».\n"
    "За час до начала пришлю напоминание ⏰\n\n"
    "<b>Команды:</b>\n"
    "/start — начать заново\n"
    "/help — эта справка"
)


# ==========================================================
#   СОЗДАНИЕ ИГРЫ
# ==========================================================

ASK_SPORT = "Во что играем? 🏆"
ASK_CUSTOM_SPORT = f"Напиши вид спорта текстом (до {CUSTOM_TEXT_MAX_LEN} символов):"
BAD_SPORT = "Выбери вид спорта кнопкой или нажми «Другое» 👇"
BAD_CUSTOM_SPORT = (
    f"Слишком длинно. Напиши покороче, до {CUSTOM_TEXT_MAX_LEN} символов:"
)

ASK_DAY = "Когда играем? 📅"
ASK_CUSTOM_DAY = "Напиши дату в формате ДД.ММ — например, 25.09"
BAD_DAY = "Выбери день кнопкой или нажми «Другая дата» 👇"
BAD_CUSTOM_DAY = "Не понял дату 🤔 Нужен формат ДД.ММ — например, 25.09"

ASK_TIME = "Во сколько? 🕒"
ASK_CUSTOM_TIME = "Напиши время в формате ЧЧ:ММ — например, 16:45"
BAD_TIME = "Выбери время кнопкой или нажми «Другое» 👇"
BAD_CUSTOM_TIME = "Не понял время 🤔 Нужен формат ЧЧ:ММ — например, 16:45"

ASK_PLACE = "Где играем? 📍"
ASK_CUSTOM_PLACE = f"Напиши место текстом (до {CUSTOM_TEXT_MAX_LEN} символов):"
BAD_PLACE = "Выбери место кнопкой или нажми «Другое» 👇"
BAD_CUSTOM_PLACE = (
    f"Слишком длинно. Напиши покороче, до {CUSTOM_TEXT_MAX_LEN} символов:"
)

ASK_PLAYERS = "Сколько человек нужно минимум? 👥"
ASK_CUSTOM_PLAYERS = f"Напиши число от {MIN_PLAYERS_LOW} до {MIN_PLAYERS_HIGH}:"
BAD_PLAYERS = "Выбери количество кнопкой или нажми «Другое» 👇"
BAD_CUSTOM_PLAYERS = (
    f"Нужно число от {MIN_PLAYERS_LOW} до {MIN_PLAYERS_HIGH}. Попробуй ещё раз:"
)

ASK_DURATION = "Сколько играем? ⏱"
BAD_DURATION = "Выбери длительность кнопкой 👇"

ASK_MAX = (
    "Максимум игроков? Кто не поместится — встанет в очередь\n"
    "и займёт место, если кто-то откажется."
)
BAD_MAX = "Выбери число кнопкой или нажми «Без ограничения» 👇"
BAD_CUSTOM_MAX = "Максимум не может быть меньше, чем нужно игроков. Попробуй ещё раз:"

ASK_NOTE = (
    "Добавить заметку? Например: «берите форму» или «играем 3 на 3».\n"
    "Не нужна — жми «Пропустить»."
)
BAD_NOTE = "Слишком длинно. Уложись в {limit} символов:"

CONFIRM_HEADER = "Проверь, всё верно?\n\n"

GAME_IN_PAST = (
    "Это время уже прошло ⏳ Игру в прошлом создать нельзя.\n"
    "Давай ещё раз выберем день:"
)
TOO_MANY_GAMES = (
    "У тебя уже {count} активных игр — это максимум.\n"
    "Проведи или отмени одну из них в разделе «🗓 Мои игры», и создавай новую."
)

CREATE_CANCELLED = "Ок, отменил. Ничего не создаю 👌"
GAME_CREATED = "Готово! Игра создана, зови ребят — она уже в списке 🔥\n\n"


# ==========================================================
#   СПИСОК ИГР, ЗАПИСЬ И ОТПИСКА
# ==========================================================

LIST_HEADER = "📋 Ближайшие игры:"
LIST_EMPTY = "Пока нет ни одной игры. Создай первую! 🏀"

SIGNED_UP_WAITING = "Мест нет — поставил тебя в очередь ⏳"
PROMOTED = (
    "🎉 Освободилось место, ты в основном составе!\n\n{game}"
)
PROMOTED_TOAST = "Тебя подняли из очереди в состав ✅"

SIGNED_UP = "Записал тебя ✅"
SIGNED_OUT = "Отписал. Ничего страшного 👌"
ALREADY_SIGNED = "Ты уже записан на эту игру"
NOT_SIGNED = "Ты и так не записан"
GAME_NOT_ACTUAL = "Эта игра уже неактуальна"
SHARE_HINT = (
    "Перешли это сообщение в чат класса — кто нажмёт на ссылку, сразу попадёт на игру 👇"
)
SHARE_MESSAGE = (
    "{emoji} <b>{sport}</b> — {when}\n"
    "📍 {place}\n"
    "{need}\n\n"
    "👉 {link}"
)
SHARE_NEED_MORE = "Нужно ещё {count} {word} — залетай!"
SHARE_ENOUGH = "Команда уже собрана, но лишним никто не будет 😄"
DEEP_LINK_NOT_FOUND = "Такой игры больше нет — возможно, её отменили."
DEEP_LINK_NEED_START = (
    "Сначала познакомимся, а потом сразу покажу игру 👇"
)
GAME_INACTIVE_CARD = "\n\n<i>Игра уже неактуальна</i>"
CREATOR_CANT_LEAVE = "Ты организатор — отписаться нельзя. Можно отменить игру."

TEAM_READY = "✅ Команда собрана! {game}. Нас уже {count}."
SOMEONE_LEFT = "Один человек отписался с игры «{game}», не хватает {missing} {word}."


# ==========================================================
#   МОИ ИГРЫ
# ==========================================================

MY_ORGANIZE_HEADER = "🙋 <b>Ты организуешь:</b>"
MY_SIGNED_HEADER = "✅ <b>Ты записан:</b>"
MY_EMPTY = (
    "У тебя пока нет игр 🤷\n\n"
    "Загляни в «📋 Список игр» и запишись к кому-нибудь, "
    "или создай свою через «🏀 Создать игру»."
)

CANCEL_GAME_CONFIRM = "Точно отменить эту игру? Всем записавшимся придёт уведомление."
CANCEL_GAME_DONE = "Игра отменена. Ребятам сообщил 👌"
CANCEL_GAME_NOT_YOURS = "Отменить игру может только её организатор"
CANCEL_GAME_KEPT = "Ок, игра остаётся 👌"
GAME_CANCELLED_FOR_PLAYERS = "❌ Игра отменена организатором.\n\n{game}"


# ==========================================================
#   ПРОФИЛЬ
# ==========================================================

PROFILE_ASK_GRADE = "В какой ты теперь параллели?"
PROFILE_ASK_LETTER = "А буква какая? Если твоей нет на кнопках — нажми «Другое»"
PROFILE_CLASS_UPDATED = "Готово, теперь ты {grade}{letter} ✅"

PROFILE_ASK_NAME = (
    "Напиши, как тебя записать — это имя увидят ребята в карточках игр.\n"
    f"До {CUSTOM_TEXT_MAX_LEN} символов."
)
PROFILE_BAD_NAME = (
    f"Имя должно быть от 2 до {CUSTOM_TEXT_MAX_LEN} символов. Попробуй ещё раз:"
)
PROFILE_NAME_UPDATED = "Готово, теперь тебя зовут {name} ✅"
PROFILE_EDIT_CANCELLED = "Ок, оставил как было 👌"


# ==========================================================
#   НАПОМИНАНИЕ
# ==========================================================

REMINDER = "⏰ Через час игра: {game}. Нас {count}."


# ==========================================================
#   АДМИНКА
# ==========================================================

NOT_ADMIN = "Эта команда только для организатора проекта"

STATS_TEMPLATE = (
    f"📊 <b>Статистика {BOT_NAME}</b>\n\n"
    "👤 <b>Пользователей:</b> {users_total}\n"
    "{grades_block}\n"
    "🏀 <b>Игры</b>\n"
    "Создано: {games_total}\n"
    "Состоялось: {games_done}\n"
    "Отменено: {games_cancelled}\n\n"
    "🙋 <b>Участие</b>\n"
    "Уникальных участников: {unique_players}\n"
    "Средний размер команды: {avg_team}\n"
    "Самый популярный спорт: {top_sport}\n\n"
    "🤝 <b>Играли с человеком из другого класса:</b> {cross_class} чел.\n"
    "😴 <b>Давно не играли (или ни разу):</b> {inactive} чел."
)

EXPORT_CAPTION = "Выгрузка по состоянию на {date}"
EXPORT_EMPTY = "В базе пока пусто — выгружать нечего."


# ==========================================================
#   ПОМОЩНИКИ: КРАСИВАЯ ДАТА И КАРТОЧКА ИГРЫ
# ==========================================================

# Месяцы в родительном падеже: «18 августа»
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

# Дни недели, короткие
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def format_date_full(game_date: str) -> str:
    """'2026-08-18' -> 'Завтра, 18 августа (вт)'"""
    day = datetime.strptime(game_date, "%Y-%m-%d").date()
    delta = (day - now().date()).days

    prefix = ""
    if delta == 0:
        prefix = "Сегодня, "
    elif delta == 1:
        prefix = "Завтра, "
    elif delta == 2:
        prefix = "Послезавтра, "

    return f"{prefix}{day.day} {MONTHS[day.month - 1]} ({WEEKDAYS[day.weekday()]})"


def format_date_short(game_date: str) -> str:
    """'2026-08-18' -> 'завтра' или '18 августа' — для коротких сообщений."""
    day = datetime.strptime(game_date, "%Y-%m-%d").date()
    delta = (day - now().date()).days

    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta == 2:
        return "послезавтра"
    return f"{day.day} {MONTHS[day.month - 1]}"


def players_word(count: int) -> str:
    """Правильное слово после числа: 'не хватает 1 игрока' / '3 игроков'."""
    return "игрока" if count == 1 else "игроков"


def format_players_list(players) -> str:
    """Имена и классы записавшихся, одной строкой через запятую."""
    names = []
    for player in players:
        name = html.escape(player["first_name"] or "Кто-то")
        if player["grade"]:
            names.append(f"{name} ({player['grade']}{player['letter']})")
        else:
            names.append(name)
    return ", ".join(names)


def format_time_range(game_time: str, duration_min) -> str:
    """'15:30' + 90 минут -> '15:30 – 17:00 (1,5 часа)'"""
    minutes = duration_min or DEFAULT_DURATION
    start = datetime.strptime(game_time, "%H:%M")
    finish = start + timedelta(minutes=minutes)
    label = DURATIONS.get(minutes, f"{minutes} мин")
    return f"{game_time} – {finish.strftime('%H:%M')} ({label})"


def days_word(count: int) -> str:
    """1 день / 2 дня / 5 дней."""
    if count % 10 == 1 and count % 100 != 11:
        return "день"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "дня"
    return "дней"


def format_last_played(last_date) -> str:
    """Когда человек играл последний раз — человеческими словами."""
    if last_date is None:
        return "ещё ни разу"

    days = (now().date() - datetime.strptime(last_date, "%Y-%m-%d").date()).days
    if days <= 0:
        return "сегодня"
    if days == 1:
        return "вчера"
    if days < 30:
        return f"{days} {days_word(days)} назад"
    months = days // 30
    return "больше месяца назад" if months <= 1 else f"больше {months} мес. назад"


def format_game_card(game, players=None, waiting=None) -> str:
    """
    Собирает карточку игры — то, что видно в списке.

    game    — строка из базы (поля игры + players_count + данные организатора)
    players — основной состав; если передан, будут видны имена
    waiting — очередь; показывается, только если в ней кто-то есть
    """
    sport = game["sport"]
    emoji = sport_emoji(sport)

    # Организатор мог не успеть зарегистрироваться — подстрахуемся
    creator_name = game["creator_name"] or "Кто-то"
    if game["creator_grade"]:
        creator = f"{creator_name} ({game['creator_grade']}{game['creator_letter']})"
    else:
        creator = creator_name

    count = game["players_count"]
    ready = " ✅" if count >= game["min_players"] else ""

    # Номер игры — по нему удобно ссылаться: «пойдём на 12-ю»
    number = f" · #{game['game_id']}" if game.get("game_id") else ""

    # Заметка организатора — отдельной строкой, если она есть
    note = f"💬 {html.escape(game['note'])}\n" if game.get("note") else ""

    # Когда мест больше нет, честно об этом пишем
    max_players = game.get("max_players")
    no_seats = " · мест больше нет" if max_players and count >= max_players else ""

    roster = "\n   " + format_players_list(players) if players else ""

    # Очередь показываем, только когда в ней реально кто-то стоит
    queue = ""
    if waiting:
        queue = (f"⏳ В очереди: {len(waiting)}\n"
                 f"   {format_players_list(waiting)}\n")

    return (
        f"{emoji} <b>{html.escape(sport)}</b>{number}\n"
        f"📅 {format_date_full(game['game_date'])}\n"
        f"🕒 {format_time_range(game['game_time'], game.get('duration_min'))}\n"
        f"📍 {html.escape(game['place'])}\n"
        f"{note}"
        f"👥 Записались: {count} из {game['min_players']}{ready}{no_seats}{roster}\n"
        f"{queue}"
        f"🙋 Организатор: {html.escape(creator)}"
    )


def format_game_short(game) -> str:
    """Короткая строчка для уведомлений: 'Баскетбол, завтра в 15:30, площадка за школой'."""
    return (
        f"{html.escape(game['sport'])}, "
        f"{format_date_short(game['game_date'])} в {game['game_time']}, "
        f"{html.escape(game['place'].lower())}"
    )


def classes_word(count: int) -> str:
    """Правильное слово после числа: «из 1 класса» / «из 4 классов»."""
    if count % 10 == 1 and count % 100 != 11:
        return "класса"
    return "классов"


def format_profile(user, stats, last_date=None) -> str:
    """
    Собирает экран профиля: данные человека плюс его личная статистика.
    user  — строка из таблицы users
    stats — то, что вернула database.get_profile_stats()
    """
    name = html.escape(user["first_name"] or "Без имени")
    nick = f"@{html.escape(user['username'])}" if user["username"] else "не указан"

    # created_at выглядит как '2026-08-18 00:11:15' — берём из него только дату
    if user["created_at"]:
        day = datetime.strptime(user["created_at"][:10], "%Y-%m-%d").date()
        joined = f"{day.day} {MONTHS[day.month - 1]}"
    else:
        joined = "давно"

    favourite = html.escape(stats["favourite"]) if stats["favourite"] else "пока не ясно"
    last_played = format_last_played(last_date)

    met = stats["classes_met"]
    met_text = f"с ребятами из {met} {classes_word(met)}" if met else "пока только один"

    return (
        "👤 <b>Твой профиль</b>\n\n"
        f"Имя: <b>{name}</b>\n"
        f"Класс: <b>{user['grade']}{user['letter']}</b>\n"
        f"Ник: {nick}\n"
        f"В {BOT_NAME} с {joined}\n\n"
        "📊 <b>Твоя статистика</b>\n"
        f"Организовал игр: {stats['created']}\n"
        f"Участвовал в играх: {stats['joined']}\n"
        f"Любимый спорт: {favourite}\n"
        f"Последняя игра: {last_played}\n"
        f"Играл {met_text}"
    )


def sport_emoji(sport: str) -> str:
    """Значок вида спорта. Если его нет в config.py — общий 🏅"""
    return SPORT_EMOJI.get(sport, DEFAULT_SPORT_EMOJI)
