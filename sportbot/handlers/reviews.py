"""
Отзывы об играх.

После игры бот сам присылает участникам просьбу оценить её от 1 до 5.
Оценка ставится одной кнопкой, комментарий — по желанию.
Отзыв уходит организатору этой игры, чтобы он понимал, как всё прошло.
"""

import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts
from config import NOTE_MAX_LEN
from scheduler import safe_send

logger = logging.getLogger(__name__)
router = Router(name="reviews")


class Review(StatesGroup):
    """Единственный шаг с вводом текста — необязательный комментарий."""
    comment = State()


async def notify_organizer(bot: Bot, game_id: int, author, rating: int,
                           comment: str | None) -> None:
    """Показывает организатору отзыв о его игре."""
    game = await db.get_game(game_id)
    if game is None or game["creator_id"] == author["user_id"]:
        return                     # свой же отзыв организатору не шлём

    name = html.escape(author["first_name"] or "Кто-то")
    if author["grade"]:
        name = f"{name} ({author['grade']}{author['letter']})"

    tail = f"\n\n«{html.escape(comment)}»" if comment else ""

    await safe_send(bot, game["creator_id"], texts.REVIEW_FOR_ORGANIZER.format(
        game=texts.format_game_short(game),
        stars=texts.stars(rating),
        author=name,
        comment=tail,
    ))


# ==========================================================
#   ОЦЕНКА ОДНОЙ КНОПКОЙ
# ==========================================================

@router.callback_query(F.data.startswith("rate:"))
async def save_rating(callback: CallbackQuery, state: FSMContext) -> None:
    _, game_text, value_text = callback.data.split(":")
    game_id, rating = int(game_text), int(value_text)
    user_id = callback.from_user.id

    game = await db.get_game(game_id)
    if game is None or game["status"] == "deleted":
        await callback.answer(texts.REVIEW_GAME_GONE, show_alert=True)
        return

    if not await db.add_review(game_id, user_id, rating):
        await callback.answer(texts.REVIEW_ALREADY, show_alert=True)
        return

    await callback.answer(texts.REVIEW_THANKS)
    logger.info("Пользователь %s оценил игру #%s на %s", user_id, game_id, rating)

    # Убираем кнопки, чтобы нельзя было нажать второй раз
    try:
        await callback.message.edit_text(
            f"{texts.stars(rating)}\n\n{texts.format_game_short(game)}")
    except TelegramBadRequest as error:
        logger.debug("Сообщение с оценкой не изменилось: %s", error)

    # Запоминаем игру и оценку — пригодятся на следующем шаге
    await state.update_data(review_game_id=game_id, review_rating=rating)
    await state.set_state(Review.comment)
    await callback.message.answer(texts.REVIEW_ASK_COMMENT,
                                  reply_markup=kb.review_comment_kb())


# ==========================================================
#   НЕОБЯЗАТЕЛЬНЫЙ КОММЕНТАРИЙ
# ==========================================================

@router.message(Review.comment, F.text == texts.BTN_SKIP_COMMENT)
async def skip_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    """Проверяется раньше обычного текста."""
    data = await state.get_data()
    await state.clear()

    author = await db.get_user(message.from_user.id)
    if author:
        await notify_organizer(bot, data["review_game_id"], author,
                               data["review_rating"], None)

    await message.answer(texts.REVIEW_THANKS, reply_markup=kb.main_menu())


@router.message(Review.comment)
async def save_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()

    if len(text) > NOTE_MAX_LEN:
        await message.answer(texts.REVIEW_BAD_COMMENT.format(limit=NOTE_MAX_LEN),
                             reply_markup=kb.review_comment_kb())
        return

    data = await state.get_data()
    game_id = data["review_game_id"]
    rating = data["review_rating"]
    await state.clear()

    await db.set_review_comment(game_id, message.from_user.id, text)
    logger.info("Пользователь %s оставил комментарий к игре #%s",
                message.from_user.id, game_id)

    author = await db.get_user(message.from_user.id)
    if author:
        await notify_organizer(bot, game_id, author, rating, text)

    await message.answer(texts.REVIEW_THANKS, reply_markup=kb.main_menu())
