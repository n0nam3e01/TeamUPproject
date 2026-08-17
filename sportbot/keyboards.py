"""
Все клавиатуры и кнопки бота.

Два вида клавиатур:
  ReplyKeyboard — обычные кнопки внизу экрана (главное меню, шаги создания игры)
  InlineKeyboard — кнопки прямо под сообщением (записаться / отписаться / отменить)

Надписи на кнопках лежат в texts.py, списки вариантов — в config.py.
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import texts
from config import GRADES, LETTERS, PLACES, PLAYER_COUNTS, SPORTS, TIMES


def _rows(items: list[str], per_row: int) -> list[list[KeyboardButton]]:
    """Раскладывает список надписей по рядам, по per_row кнопок в каждом."""
    buttons = [KeyboardButton(text=item) for item in items]
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def _reply_kb(items: list[str], per_row: int,
              with_cancel: bool = False) -> ReplyKeyboardMarkup:
    """Собирает обычную клавиатуру. with_cancel=True добавляет «⬅️ Отмена» снизу."""
    keyboard = _rows(items, per_row)
    if with_cancel:
        keyboard.append([KeyboardButton(text=texts.BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ==========================================================
#   ГЛАВНОЕ МЕНЮ И РЕГИСТРАЦИЯ
# ==========================================================

def main_menu() -> ReplyKeyboardMarkup:
    """Нижнее меню — видно почти всегда."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_CREATE), KeyboardButton(text=texts.BTN_LIST)],
            [KeyboardButton(text=texts.BTN_MY), KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def grades_kb() -> ReplyKeyboardMarkup:
    """Кнопки с номерами классов: 7 8 9 10 11"""
    return _reply_kb([str(grade) for grade in GRADES], per_row=5)


def letters_kb() -> ReplyKeyboardMarkup:
    """Кнопки с буквами классов: А Б В Г Д"""
    return _reply_kb(LETTERS, per_row=5)


# ==========================================================
#   ШАГИ СОЗДАНИЯ ИГРЫ
# ==========================================================

def sports_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(SPORTS + [texts.BTN_OTHER], per_row=2, with_cancel=True)


def days_kb() -> ReplyKeyboardMarkup:
    days = [texts.BTN_TODAY, texts.BTN_TOMORROW,
            texts.BTN_AFTER_TOMORROW, texts.BTN_OTHER_DATE]
    return _reply_kb(days, per_row=2, with_cancel=True)


def times_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(TIMES + [texts.BTN_OTHER], per_row=3, with_cancel=True)


def places_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(PLACES + [texts.BTN_OTHER], per_row=1, with_cancel=True)


def players_kb() -> ReplyKeyboardMarkup:
    counts = [str(count) for count in PLAYER_COUNTS]
    return _reply_kb(counts + [texts.BTN_OTHER], per_row=3, with_cancel=True)


def only_cancel_kb() -> ReplyKeyboardMarkup:
    """Клавиатура для шагов, где нужно ввести текст руками."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_CANCEL)]],
        resize_keyboard=True,
    )


def confirm_kb() -> ReplyKeyboardMarkup:
    """Последний шаг: создать игру или передумать."""
    return _reply_kb([texts.BTN_CONFIRM_YES, texts.BTN_CONFIRM_NO], per_row=2)


# ==========================================================
#   КНОПКИ ПОД КАРТОЧКОЙ ИГРЫ
# ==========================================================

def game_card_kb(game_id: int, signed_up: bool,
                 is_creator: bool) -> InlineKeyboardMarkup:
    """
    Кнопка под карточкой игры зависит от того, кто смотрит:
      организатор  -> «Отменить игру»
      записан      -> «Отписаться»
      не записан   -> «Записаться»
    """
    if is_creator:
        button = InlineKeyboardButton(
            text=texts.BTN_CANCEL_GAME, callback_data=f"cancelgame:{game_id}"
        )
    elif signed_up:
        button = InlineKeyboardButton(
            text=texts.BTN_SIGNOUT, callback_data=f"signout:{game_id}"
        )
    else:
        button = InlineKeyboardButton(
            text=texts.BTN_SIGNUP, callback_data=f"signup:{game_id}"
        )

    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def cancel_game_confirm_kb(game_id: int) -> InlineKeyboardMarkup:
    """Подтверждение отмены игры — чтобы не удалить случайно."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.BTN_CANCEL_GAME_YES,
                             callback_data=f"cancelyes:{game_id}"),
        InlineKeyboardButton(text=texts.BTN_CANCEL_GAME_NO,
                             callback_data=f"cancelno:{game_id}"),
    ]])


def create_first_kb() -> InlineKeyboardMarkup:
    """Кнопка «Создать игру» под сообщением о пустом списке."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.BTN_CREATE_FIRST, callback_data="createnew"),
    ]])
