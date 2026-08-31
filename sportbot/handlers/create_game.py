"""
Пошаговое создание игры.

Шаги идут по очереди (это называется FSM — «машина состояний»):
спорт -> день -> время -> длительность -> место -> сколько игроков ->
максимум игроков -> заметка -> подтверждение.

На каждом шаге бот помнит, что уже выбрано, и ждёт ответ только на текущий вопрос.
Кнопка «⬅️ Отмена» на любом шаге возвращает в главное меню.
"""

import logging
from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts
from config import (
    CUSTOM_TEXT_MAX_LEN,
    DURATIONS,
    MAX_PLAYER_OPTIONS,
    NOTE_MAX_LEN,
    MAX_ACTIVE_GAMES,
    MIN_PLAYERS_HIGH,
    MIN_PLAYERS_LOW,
    PLACES,
    PLAYER_COUNTS,
    SPORTS,
    TIMES,
    game_datetime,
    now,
)

logger = logging.getLogger(__name__)
router = Router(name="create_game")


class CreateGame(StatesGroup):
    """Все шаги создания игры. Шаги с приставкой custom_ — это ручной ввод."""
    sport = State()
    custom_sport = State()
    day = State()
    custom_day = State()
    time = State()
    custom_time = State()
    duration = State()
    place = State()
    custom_place = State()
    players = State()
    custom_players = State()
    max_players = State()
    note = State()
    confirm = State()


# ==========================================================
#   МАЛЕНЬКИЕ ПОМОЩНИКИ
# ==========================================================

def parse_custom_date(text: str) -> str | None:
    """
    Превращает «25.09» в «2026-09-25». Возвращает None, если введена ерунда.
    Если такая дата в этом году уже прошла — считаем, что речь о следующем годе.
    """
    parts = text.strip().replace("/", ".").replace("-", ".").split(".")
    if len(parts) != 2:
        return None

    try:
        day_number, month_number = int(parts[0]), int(parts[1])
        today = now().date()
        result = date(today.year, month_number, day_number)
        if result < today:
            result = date(today.year + 1, month_number, day_number)
    except ValueError:
        return None

    return result.isoformat()


def parse_custom_time(text: str) -> str | None:
    """Превращает «16:45» в «16:45», проверяя, что это вообще время. Иначе None."""
    cleaned = text.strip().replace(".", ":").replace("-", ":").replace(" ", "")
    try:
        moment = datetime.strptime(cleaned, "%H:%M")
    except ValueError:
        return None
    return moment.strftime("%H:%M")


async def build_preview(state: FSMContext, user: dict) -> str:
    """Собирает карточку игры для шага подтверждения — игры в базе ещё нет."""
    data = await state.get_data()
    preview = {
        "sport": data["sport"],
        "game_date": data["game_date"],
        "game_time": data["game_time"],
        "place": data["place"],
        "min_players": data["min_players"],
        "max_players": data.get("max_players"),
        "duration_min": data["duration_min"],
        "note": data.get("note"),
        "players_count": 1,               # организатор считается первым игроком
        "creator_name": user["first_name"],
        "creator_grade": user["grade"],
        "creator_letter": user["letter"],
    }
    return texts.format_game_card(preview)


async def ask_day(message: Message, state: FSMContext) -> None:
    """Спрашиваем день. Вынесено отдельно, потому что сюда же возвращаемся из-за ошибки."""
    await message.answer(texts.ASK_DAY, reply_markup=kb.days_kb())
    await state.set_state(CreateGame.day)


async def start_creation(message: Message, state: FSMContext) -> None:
    """
    Начало создания игры: проверяем человека и лимит игр, потом спрашиваем спорт.

    Здесь и ниже берём message.chat.id, а не message.from_user.id: сюда можно
    попасть и по нажатию инлайн-кнопки, а у такого сообщения автор — сам бот.
    В личной переписке chat.id — это и есть telegram id человека.
    """
    user = await db.get_user(message.chat.id)
    if user is None:
        await message.answer(texts.NEED_START)
        return

    # Запрет на создание игр — записываться на чужие он не мешает
    ban = await db.get_ban(message.chat.id)
    if ban:
        await message.answer(
            texts.CANNOT_CREATE_BANNED.format(until=texts.format_ban_until(ban)),
            reply_markup=kb.main_menu())
        return

    active = await db.count_active_games(message.chat.id)
    if active >= MAX_ACTIVE_GAMES:
        await message.answer(texts.TOO_MANY_GAMES.format(count=active),
                             reply_markup=kb.main_menu())
        return

    await state.clear()
    await message.answer(texts.ASK_SPORT, reply_markup=kb.sports_kb())
    await state.set_state(CreateGame.sport)


# ==========================================================
#   ОТМЕНА — должна проверяться раньше всех остальных шагов
# ==========================================================

@router.message(StateFilter(CreateGame), F.text == texts.BTN_CANCEL)
async def cancel_creation(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CREATE_CANCELLED, reply_markup=kb.main_menu())


# ==========================================================
#   ВХОД: кнопка меню или кнопка под пустым списком игр
# ==========================================================

@router.message(StateFilter(None), F.text == texts.BTN_CREATE)
async def menu_create(message: Message, state: FSMContext) -> None:
    await start_creation(message, state)


@router.callback_query(F.data == "createnew")
async def button_create(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await start_creation(callback.message, state)


# ==========================================================
#   ШАГ 1: ВИД СПОРТА
# ==========================================================

@router.message(CreateGame.sport)
async def step_sport(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == texts.BTN_OTHER:
        await message.answer(texts.ASK_CUSTOM_SPORT, reply_markup=kb.only_cancel_kb())
        await state.set_state(CreateGame.custom_sport)
        return

    if text not in SPORTS:
        await message.answer(texts.BAD_SPORT, reply_markup=kb.sports_kb())
        return

    await state.update_data(sport=text)
    await ask_day(message, state)


@router.message(CreateGame.custom_sport)
async def step_custom_sport(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if not text or len(text) > CUSTOM_TEXT_MAX_LEN:
        await message.answer(texts.BAD_CUSTOM_SPORT, reply_markup=kb.only_cancel_kb())
        return

    await state.update_data(sport=text)
    await ask_day(message, state)


# ==========================================================
#   ШАГ 2: ДЕНЬ
# ==========================================================

@router.message(CreateGame.day)
async def step_day(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    today = now().date()

    if text == texts.BTN_TODAY:
        game_date = today
    elif text == texts.BTN_TOMORROW:
        game_date = today + timedelta(days=1)
    elif text == texts.BTN_AFTER_TOMORROW:
        game_date = today + timedelta(days=2)
    elif text == texts.BTN_OTHER_DATE:
        await message.answer(texts.ASK_CUSTOM_DAY, reply_markup=kb.only_cancel_kb())
        await state.set_state(CreateGame.custom_day)
        return
    else:
        await message.answer(texts.BAD_DAY, reply_markup=kb.days_kb())
        return

    await state.update_data(game_date=game_date.isoformat())
    await message.answer(texts.ASK_TIME, reply_markup=kb.times_kb())
    await state.set_state(CreateGame.time)


@router.message(CreateGame.custom_day)
async def step_custom_day(message: Message, state: FSMContext) -> None:
    game_date = parse_custom_date(message.text or "")

    if game_date is None:
        await message.answer(texts.BAD_CUSTOM_DAY, reply_markup=kb.only_cancel_kb())
        return

    await state.update_data(game_date=game_date)
    await message.answer(texts.ASK_TIME, reply_markup=kb.times_kb())
    await state.set_state(CreateGame.time)


# ==========================================================
#   ШАГ 3: ВРЕМЯ (и проверка, что игра не в прошлом)
# ==========================================================

async def apply_time(message: Message, state: FSMContext, game_time: str) -> None:
    """Сохраняет время и проверяет, что момент игры ещё не наступил."""
    data = await state.get_data()
    moment = game_datetime({"game_date": data["game_date"], "game_time": game_time})

    if moment <= now():
        # Игру в прошлом создать нельзя — возвращаемся к выбору дня
        await message.answer(texts.GAME_IN_PAST)
        await ask_day(message, state)
        return

    await state.update_data(game_time=game_time)
    await message.answer(texts.ASK_DURATION, reply_markup=kb.durations_kb())
    await state.set_state(CreateGame.duration)


@router.message(CreateGame.time)
async def step_time(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == texts.BTN_OTHER:
        await message.answer(texts.ASK_CUSTOM_TIME, reply_markup=kb.only_cancel_kb())
        await state.set_state(CreateGame.custom_time)
        return

    if text not in TIMES:
        await message.answer(texts.BAD_TIME, reply_markup=kb.times_kb())
        return

    await apply_time(message, state, text)


@router.message(CreateGame.custom_time)
async def step_custom_time(message: Message, state: FSMContext) -> None:
    game_time = parse_custom_time(message.text or "")

    if game_time is None:
        await message.answer(texts.BAD_CUSTOM_TIME, reply_markup=kb.only_cancel_kb())
        return

    await apply_time(message, state, game_time)


# ==========================================================
#   ШАГ 4: СКОЛЬКО ДЛИТСЯ ИГРА
# ==========================================================

@router.message(CreateGame.duration)
async def step_duration(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    # DURATIONS хранит минуты -> надпись; ищем минуты по надписи
    minutes = next((m for m, label in DURATIONS.items() if label == text), None)
    if minutes is None:
        await message.answer(texts.BAD_DURATION, reply_markup=kb.durations_kb())
        return

    await state.update_data(duration_min=minutes)
    await message.answer(texts.ASK_PLACE, reply_markup=kb.places_kb())
    await state.set_state(CreateGame.place)


# ==========================================================
#   ШАГ 5: МЕСТО
# ==========================================================

@router.message(CreateGame.place)
async def step_place(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == texts.BTN_OTHER:
        await message.answer(texts.ASK_CUSTOM_PLACE, reply_markup=kb.only_cancel_kb())
        await state.set_state(CreateGame.custom_place)
        return

    if text not in PLACES:
        await message.answer(texts.BAD_PLACE, reply_markup=kb.places_kb())
        return

    await state.update_data(place=text)
    await message.answer(texts.ASK_PLAYERS, reply_markup=kb.players_kb())
    await state.set_state(CreateGame.players)


@router.message(CreateGame.custom_place)
async def step_custom_place(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if not text or len(text) > CUSTOM_TEXT_MAX_LEN:
        await message.answer(texts.BAD_CUSTOM_PLACE, reply_markup=kb.only_cancel_kb())
        return

    await state.update_data(place=text)
    await message.answer(texts.ASK_PLAYERS, reply_markup=kb.players_kb())
    await state.set_state(CreateGame.players)


# ==========================================================
#   ШАГ 5: СКОЛЬКО НУЖНО ИГРОКОВ
# ==========================================================

async def show_confirm(message: Message, state: FSMContext) -> None:
    """Показывает итоговую карточку и две кнопки: создать или отменить."""
    user = await db.get_user(message.chat.id)
    if user is None:
        await state.clear()
        await message.answer(texts.NEED_START, reply_markup=kb.main_menu())
        return

    card = await build_preview(state, user)
    await message.answer(texts.CONFIRM_HEADER + card, reply_markup=kb.confirm_kb())
    await state.set_state(CreateGame.confirm)


@router.message(CreateGame.players)
async def step_players(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == texts.BTN_OTHER:
        await message.answer(texts.ASK_CUSTOM_PLAYERS, reply_markup=kb.only_cancel_kb())
        await state.set_state(CreateGame.custom_players)
        return

    if text not in [str(count) for count in PLAYER_COUNTS]:
        await message.answer(texts.BAD_PLAYERS, reply_markup=kb.players_kb())
        return

    await state.update_data(min_players=int(text))
    await ask_max(message, state)


@router.message(CreateGame.custom_players)
async def step_custom_players(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if not text.isdigit() or not MIN_PLAYERS_LOW <= int(text) <= MIN_PLAYERS_HIGH:
        await message.answer(texts.BAD_CUSTOM_PLAYERS, reply_markup=kb.only_cancel_kb())
        return

    await state.update_data(min_players=int(text))
    await ask_max(message, state)


# ==========================================================
#   ШАГ 7: ПОТОЛОК СОСТАВА И ЗАМЕТКА
# ==========================================================

async def ask_max(message: Message, state: FSMContext) -> None:
    await message.answer(texts.ASK_MAX, reply_markup=kb.max_players_kb())
    await state.set_state(CreateGame.max_players)


async def ask_note(message: Message, state: FSMContext) -> None:
    await message.answer(texts.ASK_NOTE, reply_markup=kb.note_kb())
    await state.set_state(CreateGame.note)


async def save_max(message: Message, state: FSMContext, value) -> None:
    """Проверяет, что потолок не меньше нужного количества, и идёт дальше."""
    data = await state.get_data()
    if value is not None and value < data["min_players"]:
        await message.answer(texts.BAD_CUSTOM_MAX, reply_markup=kb.max_players_kb())
        await state.set_state(CreateGame.max_players)
        return

    await state.update_data(max_players=value)
    await ask_note(message, state)


@router.message(CreateGame.max_players)
async def step_max(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == texts.BTN_NO_LIMIT:
        await save_max(message, state, None)
        return

    if text not in [str(count) for count in MAX_PLAYER_OPTIONS]:
        await message.answer(texts.BAD_MAX, reply_markup=kb.max_players_kb())
        return

    await save_max(message, state, int(text))


@router.message(CreateGame.note)
async def step_note(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == texts.BTN_SKIP:
        await state.update_data(note=None)
        await show_confirm(message, state)
        return

    if len(text) > NOTE_MAX_LEN:
        await message.answer(texts.BAD_NOTE.format(limit=NOTE_MAX_LEN),
                             reply_markup=kb.note_kb())
        return

    await state.update_data(note=text or None)
    await show_confirm(message, state)


# ==========================================================
#   ШАГ 8: ПОДТВЕРЖДЕНИЕ И СОХРАНЕНИЕ
# ==========================================================

@router.message(CreateGame.confirm)
async def step_confirm(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == texts.BTN_CONFIRM_NO:
        await state.clear()
        await message.answer(texts.CREATE_CANCELLED, reply_markup=kb.main_menu())
        return

    if text != texts.BTN_CONFIRM_YES:
        await message.answer(texts.UNKNOWN, reply_markup=kb.confirm_kb())
        return

    data = await state.get_data()
    user_id = message.chat.id

    # Пока человек думал, лимит игр мог закончиться — проверяем ещё раз
    active = await db.count_active_games(user_id)
    if active >= MAX_ACTIVE_GAMES:
        await state.clear()
        await message.answer(texts.TOO_MANY_GAMES.format(count=active),
                             reply_markup=kb.main_menu())
        return

    # ...и время могло стать прошедшим
    moment = game_datetime({"game_date": data["game_date"],
                            "game_time": data["game_time"]})
    if moment <= now():
        await message.answer(texts.GAME_IN_PAST)
        await ask_day(message, state)
        return

    game_id = await db.create_game(
        creator_id=user_id,
        sport=data["sport"],
        game_date=data["game_date"],
        game_time=data["game_time"],
        place=data["place"],
        min_players=data["min_players"],
        max_players=data.get("max_players"),
        duration_min=data["duration_min"],
        note=data.get("note"),
    )
    await state.clear()

    logger.info(
        "Создана игра #%s: %s, %s %s, %s (организатор %s)",
        game_id, data["sport"], data["game_date"], data["game_time"],
        data["place"], user_id,
    )

    game = await db.get_game(game_id)
    await message.answer(
        texts.GAME_CREATED + texts.format_game_card(game),
        reply_markup=kb.main_menu(),
    )
