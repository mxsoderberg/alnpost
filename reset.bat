@echo off
chcp 65001 >nul
title Автоматическая публикация

cls
echo ================================
echo    АВТОМАТИЧЕСКАЯ ПУБЛИКАЦИЯ
echo ================================

cd /d C:\Users\mx\Desktop\sturm\alnpost

echo Проверка файлов...
set count=0
for %%f in (materials\*) do (
    if /i not "%%~nxf"==".gitkeep" (
        set /a count+=1
    )
)

if %count%==0 (
    echo Нет файлов для публикации!
    pause
    exit /b
)

echo Найдено %count% файлов.
echo.

echo Загрузка на GitHub (автодеплой включен)...
git add --all
git commit -m "Публикация %date% %time% (%count% файлов)"
git push origin master

if %errorlevel%==0 (
    echo.
    echo УСПЕХ! Файлы загружены.
    echo.
    echo GitHub Actions автоматически запустит деплой на Render.
    echo Это займет 1-2 минуты.
    echo.
    echo После деплоя:
    echo 1. Откройте Telegram
    echo 2. Найдите @alnpost_bot
    echo 3. Нажмите "🔄 Перезагрузить"
    echo.
    echo Открытие мониторинга...
    start "" "https://github.com/mxsoderberg/alnpost/actions"
) else (
    echo ОШИБКА загрузки!
)

pause