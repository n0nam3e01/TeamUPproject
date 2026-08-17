"""
Список ближайших игр и кнопки «Записаться» / «Отписаться».

Здесь же лежат три помощника, которыми пользуется и файл my_games.py:
  is_game_active   — жива ли ещё игра
  refresh_card     — перерисовать карточку прямо в том же сообщении
  show_dead_card   — пометить карточку как неактуальную
"""

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import database as db
import keyboards as kb
import texts
from config import GAMES_LIST_LIMIT, game_datetime, now
from scheduler import notify_players, safe_send

logger = logging.getLogger(__name__)
router = Router(name="games_list")


# ==========================================================
#   ПОМОЩНИКИ
# ==========================================================

def is_game_active(game) -> bool:
    """Игра жива, если она не отменена, не завершена и ещё не началась."""
    if game is None:
        return False
    if game["status"] not in ("open", "full"):
        return False
    return game_datetime(game) > now()


async def edit_card(callback: CallbackQuery, text: str,
                    markup: InlineKeyboardMarkup | None) -> None:
    """
    Меняет текст карточки прямо в том же сообщении — новые сообщения не плодим.
    Telegram ругается, если текст не изменился, — эту ошибку спокойно пропускаем.
    """
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as error:
        logger.debug("Карточку не пришлось обновлять: %s", error)


async def refresh_card(callback: CallbackQuery, game_id: int, user_id: int) -> None:
    """Перерисовывает карточку игры так, как её должен видеть этот пользователь."""
    game = await db.get_game(game_id)
    if game is None:
        await edit_card(callback, texts.GAME_NOT_ACTUAL, None)
        return

    if not is_game_active(game):
        await show_dead_card(callback, game)
        return

    signed_up = await db.is_signed_up(game_id, user_id)
    is_creator = game["creator_id"] == user_id

    await edit_card(
        callback,
        texts.format_game_card(game),
        kb.game_card_kb(game_id, signed_up, is_creator),
    )


async def show_dead_card(callback: CallbackQuery, game=None) -> None:
    """Игра отменилась или прошла: показываем это и убираем кнопки."""
    if game is None:
        await edit_card(callback, texts.GAME_NOT_ACTUAL, None)
        return
    await edit_card(callback, texts.format_game_card(game) + texts.GAME_INACTIVE_CARD, None)


async def send_game_card(message: Message, game, user_id: int) -> None:
    """Отправляет карточку игры отдельным сообщением с нужной кнопкой."""
    signed_up = await db.is_signed_up(game["game_id"], user_id)
    is_creator = game["creator_id"] == user_id

    await message.answer(
        texts.format_game_card(game),
        reply_markup=kb.game_card_kb(game["game_id"], signed_up, is_creator),
    )


# ==========================================================
#   СПИСОК ИГР
# ==========================================================

@router.message(StateFilter(None), F.text == texts.BTN_LIST)
async def show_games(message: Message, state: FSMContext) -> None:
    """Показывает до 10 ближайших игр, каждую — отдельной карточкой."""
    user_id = message.from_user.id

    if await db.get_user(user_id) is None:
        await message.answer(texts.NEED_START)
        return

    games = await db.get_upcoming_games(GAMES_LIST_LIMIT)

    if not games:
        await message.answer(texts.LIST_EMPTY, reply_markup=kb.create_first_kb())
        return

    await message.answer(texts.LIST_HEADER, reply_markup=kb.main_menu())
    for game in games:
        await send_game_card(message, game, user_id)


# ==========================================================
#   ЗАПИСАТЬСЯ
# ==========================================================

@router.callback_query(F.data.startswith("signup:"))
async def do_signup(callback: CallbackQuery, bot: Bot) -> None:
    game_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    if await db.get_user(user_id) is None:
        await callback.answer(texts.NEED_START, show_alert=True)
        return

    game = await db.get_game(game_id)
    if not is_game_active(game):
        await callback.answer(texts.GAME_NOT_ACTUAL, show_alert=True)
        await show_dead_card(callback, game)
        return

    added = await db.add_signup(game_id, user_id)
    if added:
        await callback.answer(texts.SIGNED_UP)
        logger.info("Пользователь %s записался на игру #%s", user_id, game_id)
    else:
        # Человек нажал кнопку дважды — дубликат не создаём, просто говорим об этом
        await callback.answer(texts.ALREADY_SIGNED)

    await check_team_ready(bot, game_id)
    await refresh_card(callback, game_id, user_id)


async def check_team_ready(bot: Bot, game_id: int) -> None:
    """
    Если народу набралось столько, сколько нужно, — один раз сообщаем об этом всем.
    Флаг notified_full не даёт отправить сообщение дважды.
    """
    game = await db.get_game(game_id)
    if game is None:
        return

    enough = game["players_count"] >= game["min_players"]
    if not enough or game["notified_full"]:
        return

    await db.set_status(game_id, "full")
    await db.set_notified_full(game_id, 1)

    text = texts.TEAM_READY.format(
        game=texts.format_game_short(game),
        count=game["players_count"],
    )
    await notify_players(bot, game_id, text)
    logger.info("Игра #%s собрана: %s игроков", game_id, game["players_count"])


# ==========================================================
#   ОТПИСАТЬСЯ
# ==========================================================

@router.callback_query(F.data.startswith("signout:"))
async def do_signout(callback: CallbackQuery, bot: Bot) -> None:
    game_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    game = await db.get_game(game_id)
    if not is_game_active(game):
        await callback.answer(texts.GAME_NOT_ACTUAL, show_alert=True)
        await show_dead_card(callback, game)
        return

    # Организатор отписаться не может — только отменить игру целиком
    if game["creator_id"] == user_id:
        await callback.answer(texts.CREATOR_CANT_LEAVE, show_alert=True)
        await refresh_card(callback, game_id, user_id)
        return

    removed = await db.remove_signup(game_id, user_id)
    if removed:
        await callback.answer(texts.SIGNED_OUT)
        logger.info("Пользователь %s отписался от игры #%s", user_id, game_id)
        await check_team_broken(bot, game_id)
    else:
        await callback.answer(texts.NOT_SIGNED)

    await refresh_card(callback, game_id, user_id)


async def check_team_broken(bot: Bot, game_id: int) -> None:
    """Если после отписки народу стало не хватать — возвращаем статус и пишем организатору."""
    game = await db.get_game(game_id)
    if game is None or game["status"] != "full":
        return

    if game["players_count"] >= game["min_players"]:
        return

    await db.set_status(game_id, "open")
    await db.set_notified_full(game_id, 0)

    missing = game["min_players"] - game["players_count"]
    text = texts.SOMEONE_LEFT.format(
        game=texts.format_game_short(game),
        missing=missing,
        word=texts.players_word(missing),
    )
    await safe_send(bot, game["creator_id"], text)
