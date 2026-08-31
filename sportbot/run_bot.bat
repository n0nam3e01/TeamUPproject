@echo off
chcp 65001 > nul
title TeamUP - бот школьных игр
cd /d "%~dp0"

echo.
echo   ==========================================
echo      TeamUP - сбор на школьные игры
echo   ==========================================
echo.

REM --- Проверка 1: установлен ли Python ---
python --version > nul 2>&1
if errorlevel 1 (
    echo   ОШИБКА: Python не найден.
    echo   Установи его с сайта python.org
    echo   и при установке поставь галочку "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

REM --- Проверка 2: есть ли файл .env с токеном ---
if not exist ".env" (
    echo   ОШИБКА: нет файла .env с токеном.
    echo   Скопируй .env.example, назови копию .env
    echo   и впиши в неё токен от @BotFather.
    echo.
    pause
    exit /b 1
)

REM --- Проверка 3: стоят ли библиотеки. Если нет - ставим ---
python -c "import aiogram" > nul 2>&1
if errorlevel 1 (
    echo   Первый запуск: устанавливаю библиотеки.
    echo   Это займёт около минуты, подожди...
    echo.
    python -m pip install -q -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   ОШИБКА: не удалось установить библиотеки.
        echo   Проверь интернет и запусти файл ещё раз.
        echo.
        pause
        exit /b 1
    )
    echo   Библиотеки установлены.
    echo.
)

echo   Запускаю бота...
echo   Чтобы остановить - нажми Ctrl+C или просто закрой это окно.
echo.

python bot.py

echo.
echo   ==========================================
echo      Бот остановлен. Окно можно закрыть.
echo   ==========================================
pause
