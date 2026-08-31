"""
Команда /start, знакомство (класс и буква), главное меню и помощь.

Здесь же живёт «ловушка» для непонятных сообщений — она должна быть
самой последней во всём боте, поэтому этот роутер подключается последним.
"""

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import database as db
import keyboards as kb
import texts
from handlers import games_list
from config import GRADES, clean_letter

logger = logging.getLogger(__name__)
# Два роутера, и это важно.
#
# commands_router подключается ПЕРВЫМ во всём боте: команды вроде /start
# должны работать всегда, даже посреди создания игры. Иначе шаг диалога
# перехватит команду и ответит «выбери вид спорта кнопкой».
#
# router подключается ПОСЛЕДНИМ: в нём регистрация и «ловушка» для
# непонятных сообщений, которая обязана проверяться после всего остального.
commands_router = Router(name="commands")
router = Router(name="start")


class Register(StatesGroup):
    """Два шага знакомства: сначала параллель, потом буква класса."""
    grade = State()
    letter = State()


# ==========================================================
#   ПЕРЕХОД ПО ССЫЛКЕ НА КОНКРЕТНУЮ ИГРУ
# ==========================================================

@commands_router.message(CommandStart(deep_link=True))
async def start_with_game(message: Message, command: CommandObject,
                          state: FSMContext) -> None:
    """
    Сюда попадают те, кто пришёл по ссылке вида t.me/бот?start=game_12.
    Показываем сразу нужную игру, чтобы человек мог записаться в один клик.
    """
    await state.clear()

    # Из ссылки приходит строка вида "game_12" — вытаскиваем номер
    argument = (command.args or "")
    if not argument.startswith("game_") or not argument[5:].isdigit():
        await cmd_start(message, state)
        return

    game_id = int(argument[5:])
    user = await db.get_user(message.from_user.id)

    # Незнакомого сначала регистрируем, игру он найдёт в списке
    if user is None:
        await message.answer(texts.WELCOME)
        await message.answer(texts.DEEP_LINK_NEED_START)
        await message.answer(texts.ASK_GRADE, reply_markup=kb.grades_kb())
        await state.set_state(Register.grade)
        return

    game = await db.get_game(game_id)
    if not games_list.is_game_active(game):
        await message.answer(texts.DEEP_LINK_NOT_FOUND, reply_markup=kb.main_menu())
        return

    await message.answer(texts.LIST_HEADER, reply_markup=kb.main_menu())
    await games_list.send_game_card(message, game, message.from_user.id)
    logger.info("Пользователь %s пришёл по ссылке на игру #%s",
                message.from_user.id, game_id)


# ==========================================================
#   /start
# ==========================================================

@commands_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Знакомимся, если человек новый. Если уже знакомы — просто показываем меню."""
    await state.clear()

    user = await db.get_user(message.from_user.id)
    if user:
        await message.answer(texts.MENU, reply_markup=kb.main_menu())
        return

    await message.answer(texts.WELCOME)
    await message.answer(texts.ASK_GRADE, reply_markup=kb.grades_kb())
    await state.set_state(Register.grade)


@router.message(Register.grade)
async def register_grade(message: Message, state: FSMContext) -> None:
    """Ждём номер класса. Если пришло что-то другое — вежливо просим ещё раз."""
    text = (message.text or "").strip()

    if text not in [str(grade) for grade in GRADES]:
        await message.answer(texts.BAD_GRADE, reply_markup=kb.grades_kb())
        return

    await state.update_data(grade=int(text))
    await message.answer(texts.ASK_LETTER, reply_markup=kb.letters_kb())
    await state.set_state(Register.letter)


@router.message(Register.letter)
async def register_letter(message: Message, state: FSMContext) -> None:
    """
    Ждём букву класса. Можно нажать кнопку, а можно написать свою букву —
    вдруг в школе есть класс «Е» или «Ж», которых нет на кнопках.
    """
    text = (message.text or "").strip()

    # Нажали «Другое» — подсказываем и остаёмся ждать букву в этом же шаге
    if text == texts.BTN_OTHER:
        await message.answer(texts.ASK_CUSTOM_LETTER)
        return

    letter = clean_letter(text)
    if letter is None:
        await message.answer(texts.BAD_LETTER, reply_markup=kb.letters_kb())
        return

    data = await state.get_data()
    grade = data["grade"]

    # Имя берём прямо из Telegram — отдельно спрашивать не надо
    first_name = message.from_user.first_name or "Друг"

    await db.add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        first_name=first_name,
        grade=grade,
        letter=letter,
    )
    await state.clear()

    logger.info("Новый пользователь: %s (%s%s)", first_name, grade, letter)

    await message.answer(
        texts.REG_DONE.format(name=html.escape(first_name), grade=grade, letter=letter),
        reply_markup=kb.main_menu(),
    )


# ==========================================================
#   ПОМОЩЬ
# ==========================================================

@commands_router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def show_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.HELP, reply_markup=kb.main_menu())


# ==========================================================
#   ЛОВУШКА ДЛЯ ВСЕГО ОСТАЛЬНОГО
# ==========================================================

@router.message(StateFilter(None))
async def unknown_message(message: Message) -> None:
    """
    Сюда попадает всё, что не подошло ни одному хендлеру выше:
    случайный текст, стикеры, фотографии. Подсказываем, что делать.
    """
    await message.answer(texts.UNKNOWN, reply_markup=kb.main_menu())
