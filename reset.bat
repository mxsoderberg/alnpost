@echo off
chcp 65001 >nul
title Полная очистка и тест

cls
echo ================================
echo    ПОЛНАЯ ОЧИСТКА И ТЕСТ
echo ================================

cd /d C:\Users\mx\Desktop\sturm\alnpost

echo.
echo ШАГ 1: Очистка всех файлов...
echo.

:: Удаление всех файлов (кроме .gitkeep и bat-файлов)
for %%f in (materials\*) do (
    if /i not "%%~nxf"==".gitkeep" (
        del "%%f" 2>nul
    )
)

for %%f in (wait\*) do (
    if /i not "%%~nxf"==".gitkeep" (
        del "%%f" 2>nul
    )
)

for %%f in (arch\*) do (
    if /i not "%%~nxf"==".gitkeep" (
        del "%%f" 2>nul
    )
)

echo Файлы очищены.
echo.

echo ШАГ 2: Создание тестовых файлов...
echo.

:: Создание тестовых файлов
echo Тестовая публикация 1 > "materials\test1.txt"
echo Тестовая публикация 2 > "materials\test2.txt"

:: Создание пустых jpg файлов для теста
copy nul "materials\test1.jpg" >nul
copy nul "materials\test2.jpg" >nul

echo Созданы тестовые файлы:
echo - test1.jpg, test1.txt
echo - test2.jpg, test2.txt
echo.

echo ШАГ 3: Загрузка на GitHub...
git add .
git commit -m "Тестовые файлы %date% %time%"
git push origin master

if %errorlevel%==0 (
    echo.
    echo УСПЕХ! Тестовые файлы загружены.
    echo.
    echo ШАГ 4: Открытие Render...
    start "" "https://dashboard.render.com"
    echo.
    echo Дальнейшие действия:
    echo 1. На Render нажмите "Manual Deploy"
    echo 2. После деплоя в Telegram:
    echo    - Отправьте /start
    echo    - Нажмите "🔄 Перезагрузить"  
    echo    - Проверьте "📊 Статистика"
) else (
    echo.
    echo ОШИБКА загрузки!
)

pause