"""
Собираем все роутеры в один список.

ПОРЯДОК ВАЖЕН: aiogram проверяет роутеры сверху вниз.
start должен быть последним, потому что в нём лежит «ловушка»
для непонятных сообщений — иначе она перехватила бы всё остальное.
"""

from handlers import admin, create_game, games_list, my_games, profile, start

routers = [
    create_game.router,
    games_list.router,
    my_games.router,
    profile.router,
    admin.router,
    start.router,
]
