"""
Раздел «👤 Профиль»: свои данные, личная статистика и их изменение.

Класс меняется кнопками прямо в сообщении — быстро и без ошибок ввода.
Имя приходится писать текстом, поэтому для него включается режим ожидания (FSM).
"""

import html
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts
from config import CUSTOM_TEXT_MAX_LEN, GRADES, LETTERS, clean_letter

logger = logging.getLogger(__name__)
router = Router(name="profile")

# Имя короче двух букв не бывает
MIN_NAME_LEN = 2


class EditProfile(StatesGroup):
    """Два шага, где нужен ввод текстом: новое имя и своя буква класса."""
    name = State()
    letter = State()


# ==========================================================
#   ПОМОЩНИКИ
# ==========================================================

async def build_profile(user_id: int) -> str | None:
    """Готовит текст профиля. Вернёт None, если человек ещё не регистрировался."""
    user = await db.get_user(user_id)
    if user is None:
        return None
    stats = await db.get_profile_stats(user_id)
    return texts.format_profile(user, stats)


async def send_profile(message: Message, user_id: int) -> None:
    """Отправляет профиль новым сообщением."""
    text = await build_profile(user_id)
    if text is None:
        await message.answer(texts.NEED_START)
        return
    await message.answer(text, reply_markup=kb.profile_kb())


async def refresh_profile(callback: CallbackQuery) -> None:
    """Перерисовывает профиль в том же сообщении — новых не плодим."""
    text = await build_profile(callback.from_user.id)
    if text is None:
        await callback.answer(texts.NEED_START, show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=kb.profile_kb())
    except TelegramBadRequest as error:
        logger.debug("Профиль не пришлось обновлять: %s", error)


# ==========================================================
#   ЭКРАН ПРОФИЛЯ
# ==========================================================

@router.message(StateFilter(None), F.text == texts.BTN_PROFILE)
async def show_profile(message: Message) -> None:
    await send_profile(message, message.from_user.id)


# ==========================================================
#   СМЕНА КЛАССА — три нажатия, всё в одном сообщении
# ==========================================================

@router.callback_query(F.data == "editclass")
async def ask_new_grade(callback: CallbackQuery) -> None:
    """Шаг 1: показываем параллели."""
    await callback.answer()
    try:
        await callback.message.edit_text(
            texts.PROFILE_ASK_GRADE, reply_markup=kb.grades_inline_kb()
        )
    except TelegramBadRequest as error:
        logger.debug("Не пришлось менять сообщение: %s", error)


@router.callback_query(F.data.startswith("setgrade:"))
async def ask_new_letter(callback: CallbackQuery) -> None:
    """Шаг 2: параллель выбрана, спрашиваем букву."""
    grade = int(callback.data.split(":")[1])
    await callback.answer()
    try:
        await callback.message.edit_text(
            texts.PROFILE_ASK_LETTER, reply_markup=kb.letters_inline_kb(grade)
        )
    except TelegramBadRequest as error:
        logger.debug("Не пришлось менять сообщение: %s", error)


@router.callback_query(F.data.startswith("setletter:"))
async def save_new_class(callback: CallbackQuery) -> None:
    """Шаг 3: сохраняем класс и возвращаем профиль."""
    _, grade_text, letter = callback.data.split(":")
    grade = int(grade_text)

    # Подстраховка на случай старой кнопки из прошлой версии бота
    if grade not in GRADES or letter not in LETTERS:
        await callback.answer(texts.BAD_LETTER, show_alert=True)
        return

    await db.update_user_class(callback.from_user.id, grade, letter)
    logger.info("Пользователь %s сменил класс на %s%s",
                callback.from_user.id, grade, letter)

    await callback.answer(
        texts.PROFILE_CLASS_UPDATED.format(grade=grade, letter=letter)
    )
    await refresh_profile(callback)


# ==========================================================
#   СВОЯ БУКВА КЛАССА — если нужной нет на кнопках
# ==========================================================

@router.callback_query(F.data.startswith("letterother:"))
async def ask_custom_letter(callback: CallbackQuery, state: FSMContext) -> None:
    """Запоминаем выбранную параллель и ждём букву текстом."""
    grade = int(callback.data.split(":")[1])

    await state.update_data(grade=grade)
    await state.set_state(EditProfile.letter)

    await callback.answer()
    await callback.message.answer(texts.PROFILE_ASK_CUSTOM_LETTER,
                                  reply_markup=kb.only_cancel_kb())


@router.message(EditProfile.letter, F.text == texts.BTN_CANCEL)
async def cancel_letter_edit(message: Message, state: FSMContext) -> None:
    """Отмена проверяется раньше, чем сама буква."""
    await state.clear()
    await message.answer(texts.PROFILE_EDIT_CANCELLED, reply_markup=kb.main_menu())
    await send_profile(message, message.from_user.id)


@router.message(EditProfile.letter)
async def save_custom_letter(message: Message, state: FSMContext) -> None:
    """Принимаем ровно один символ и сохраняем класс целиком."""
    letter = clean_letter(message.text or "")

    if letter is None:
        await message.answer(texts.BAD_CUSTOM_LETTER, reply_markup=kb.only_cancel_kb())
        return

    data = await state.get_data()
    grade = data["grade"]

    await db.update_user_class(message.from_user.id, grade, letter)
    await state.clear()
    logger.info("Пользователь %s сменил класс на %s%s (буква своя)",
                message.from_user.id, grade, letter)

    await message.answer(
        texts.PROFILE_CLASS_UPDATED.format(grade=grade, letter=letter),
        reply_markup=kb.main_menu(),
    )
    await send_profile(message, message.from_user.id)


# ==========================================================
#   СМЕНА ИМЕНИ — тут нужен ввод текстом
# ==========================================================

@router.callback_query(F.data == "editname")
async def ask_new_name(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer(texts.PROFILE_ASK_NAME,
                                  reply_markup=kb.only_cancel_kb())
    await state.set_state(EditProfile.name)


@router.message(EditProfile.name, F.text == texts.BTN_CANCEL)
async def cancel_name_edit(message: Message, state: FSMContext) -> None:
    """Отмена проверяется раньше, чем ввод имени."""
    await state.clear()
    await message.answer(texts.PROFILE_EDIT_CANCELLED, reply_markup=kb.main_menu())
    await send_profile(message, message.from_user.id)


@router.message(EditProfile.name)
async def save_new_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()

    if not MIN_NAME_LEN <= len(name) <= CUSTOM_TEXT_MAX_LEN:
        await message.answer(texts.PROFILE_BAD_NAME, reply_markup=kb.only_cancel_kb())
        return

    await db.update_user_name(message.from_user.id, name)
    await state.clear()
    logger.info("Пользователь %s сменил имя на «%s»", message.from_user.id, name)

    await message.answer(
        texts.PROFILE_NAME_UPDATED.format(name=html.escape(name)),
        reply_markup=kb.main_menu(),
    )
    await send_profile(message, message.from_user.id)
