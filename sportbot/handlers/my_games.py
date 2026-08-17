"""
Раздел «👤 Мои игры»: что человек организует и куда он записан.

Организатор может отменить свою игру — с подтверждением, чтобы не нажать случайно.
Всем записавшимся при этом приходит уведомление.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts
from handlers.games_list import (
    edit_card,
    is_game_active,
    refresh_card,
    send_game_card,
    show_dead_card,
)
from scheduler import notify_players

logger = logging.getLogger(__name__)
router = Router(name="my_games")


# ==========================================================
#   ЭКРАН «МОИ ИГРЫ»
# ==========================================================

@router.message(StateFilter(None), F.text == texts.BTN_MY)
async def show_my_games(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id

    if await db.get_user(user_id) is None:
        await message.answer(texts.NEED_START)
        return

    organized = await db.get_games_created_by(user_id)
    joined = await db.get_games_joined_by(user_id)

    if not organized and not joined:
        await message.answer(texts.MY_EMPTY, reply_markup=kb.main_menu())
        return

    if organized:
        await message.answer(texts.MY_ORGANIZE_HEADER, reply_markup=kb.main_menu())
        for game in organized:
            await send_game_card(message, game, user_id)

    if joined:
        await message.answer(texts.MY_SIGNED_HEADER, reply_markup=kb.main_menu())
        for game in joined:
            await send_game_card(message, game, user_id)


# ==========================================================
#   ОТМЕНА ИГРЫ ОРГАНИЗАТОРОМ
# ==========================================================

@router.callback_query(F.data.startswith("cancelgame:"))
async def ask_cancel(callback: CallbackQuery) -> None:
    """Первое нажатие — только спрашиваем «точно?»."""
    game_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    game = await db.get_game(game_id)
    if not is_game_active(game):
        await callback.answer(texts.GAME_NOT_ACTUAL, show_alert=True)
        await show_dead_card(callback, game)
        return

    if game["creator_id"] != user_id:
        await callback.answer(texts.CANCEL_GAME_NOT_YOURS, show_alert=True)
        return

    await callback.answer()
    await edit_card(
        callback,
        texts.format_game_card(game) + "\n\n" + texts.CANCEL_GAME_CONFIRM,
        kb.cancel_game_confirm_kb(game_id),
    )


@router.callback_query(F.data.startswith("cancelyes:"))
async def do_cancel(callback: CallbackQuery, bot: Bot) -> None:
    """Подтвердили — отменяем игру и сообщаем всем записавшимся."""
    game_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    game = await db.get_game(game_id)
    if not is_game_active(game):
        await callback.answer(texts.GAME_NOT_ACTUAL, show_alert=True)
        await show_dead_card(callback, game)
        return

    if game["creator_id"] != user_id:
        await callback.answer(texts.CANCEL_GAME_NOT_YOURS, show_alert=True)
        return

    # Сообщение собираем до отмены, пока данные игры ещё на месте
    text = texts.GAME_CANCELLED_FOR_PLAYERS.format(game=texts.format_game_short(game))
    await notify_players(bot, game_id, text, skip_user_id=user_id)

    await db.set_status(game_id, "cancelled")
    logger.info("Игра #%s отменена организатором %s", game_id, user_id)

    await callback.answer(texts.CANCEL_GAME_DONE)
    game = await db.get_game(game_id)
    await show_dead_card(callback, game)


@router.callback_query(F.data.startswith("cancelno:"))
async def keep_game(callback: CallbackQuery) -> None:
    """Передумали отменять — возвращаем карточку в обычный вид."""
    game_id = int(callback.data.split(":")[1])
    await callback.answer(texts.CANCEL_GAME_KEPT)
    await refresh_card(callback, game_id, callback.from_user.id)
