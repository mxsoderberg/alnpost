@echo off
chcp 65001 >nul
title Сброс и обновление материалов

cls
echo ================================
echo    СБРОС И ОБНОВЛЕНИЕ МАТЕРИАЛОВ
echo ================================

cd /d C:\Users\mx\Desktop\sturm\alnpost

echo.
echo Текущая папка: %cd%
echo.

echo ШАГ 1: Проверка локальных файлов
echo.

:: Показываем файлы в локальной папке materials
echo Файлы в локальной папке materials:
dir materials\*.* | findstr /v ".gitkeep"
echo.

:: Считаем количество файлов
set count=0
for %%f in (materials\*) do (
    if /i not "%%~nxf"==".gitkeep" (
        set /a count+=1
    )
)

if %count%==0 (
    echo ВНИМАНИЕ: В папке materials нет файлов!
    echo Добавьте файлы перед запуском.
    echo.
    pause
    exit /b
)

echo Найдено %count% локальных файлов.
echo.

echo ШАГ 2: Загрузка всех локальных файлов...
echo.

:: Добавляем все файлы
echo Добавление файлов...
git add --all

:: Создаем коммит
echo.
echo Создание коммита...
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "timestamp=%dt:~6,2%.%dt:~4,2%.%dt:~0,4% %dt:~8,2%:%dt:~10,2%"

git commit -m "Обновление материалов %timestamp% (%count% файлов)"

:: Загружаем на GitHub
echo.
echo Загрузка на GitHub...
git push origin master

if %errorlevel%==0 (
    echo.
    echo УСПЕХ! Файлы загружены на GitHub.
    echo.
    echo Открытие Render для деплоя...
    start "" "https://dashboard.render.com"
    echo.
    echo Дальнейшие действия:
    echo 1. На Render нажмите "Manual Deploy"
    echo 2. После деплоя в Telegram нажмите "🔄 Перезагрузить"
    echo.
) else (
    echo.
    echo ОШИБКА загрузки!
    echo Проверьте подключение к интернету.
)

echo.
pause