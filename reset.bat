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

echo ШАГ 1: Проверка локальных файлов в materials
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
    echo ВНИМАНИЕ: В локальной папке materials нет файлов!
    echo Добавьте файлы перед запуском сброса.
    echo.
    pause
    exit /b
)

echo Найдено %count% локальных файлов.
echo.

echo ШАГ 2: Подготовка к сбросу
echo.

echo Это действие:
echo 1. Очистит содержимое удаленных папок (на GitHub/Render)
echo 2. Загрузит ВСЕ локальные файлы из materials
echo.

echo Вы уверены? 
set /p confirm="Введите 'RESET' для подтверждения: "

if /i "%confirm%"=="RESET" (
    echo.
    echo ШАГ 3: Создание коммита с обновленными локальными файлами...
    echo.
    
    :: Добавляем все локальные файлы (включая существующие)
    echo Добавление всех файлов...
    git add --all
    
    :: Создаем коммит
    echo.
    echo Создание коммита...
    for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
    set "timestamp=%dt:~6,2%.%dt:~4,2%.%dt:~0,4% %dt:~8,2%:%dt:~10,2%"
    
    git commit -m "Полный сброс и обновление %timestamp% (локальные файлы: %count% шт.)"
    
    :: Загружаем на GitHub
    echo.
    echo Загрузка на GitHub...
    git push origin master
    
    if %errorlevel%==0 (
        echo.
        echo УСПЕХ! Локальные файлы загружены на GitHub.
        echo.
        echo ШАГ 4: Открытие Render для деплоя...
        start "" "https://dashboard.render.com"
        echo.
        echo Дальнейшие действия:
        echo 1. На Render нажмите "Manual Deploy"
        echo 2. После деплоя в Telegram:
        echo    - Отправьте /start
        echo    - Нажмите "🔄 Перезагрузить"
        echo    - Проверьте "📊 Статистика"
        echo.
        echo ВАЖНО: Render автоматически очистит свои папки и загрузит новые файлы
    ) else (
        echo.
        echo ОШИБКА загрузки на GitHub!
        echo Проверьте подключение к интернету.
    )
) else (
    echo.
    echo Сброс отменен.
)

echo.
pause