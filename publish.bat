@echo off
chcp 65001 >nul
title Публикация материалов

cls
echo ================================
echo    ПУБЛИКАЦИЯ МАТЕРИАЛОВ
echo ================================

cd /d C:\Users\mx\Desktop\sturm\alnpost

echo.
echo Текущая папка: %cd%
echo.

echo Содержимое папки materials:
dir materials\*.*
echo.

:: Считаем файлы, кроме .gitkeep
set count=0
for %%f in (materials\*) do (
    if /i not "%%~nxf"==".gitkeep" (
        set /a count+=1
    )
)

if %count%==0 (
    echo ОШИБКА: В папке materials нет файлов для публикации!
    echo.
    echo Добавьте файлы в формате:
    echo   - image.jpg (изображение)
    echo   - image.txt (текст к изображению)
    echo.
    pause
    exit /b
)

echo Найдено %count% файлов
echo.

echo Загрузка файлов на GitHub...
echo.

echo Добавление всех файлов в Git...
git add --all

echo.
echo Создание коммита...
git commit -m "Добавлены материалы %date% %time%"

echo.
echo Загрузка на GitHub...
git push origin master

if %errorlevel%==0 (
    echo.
    echo УСПЕХ! Файлы загружены на GitHub.
    echo.
    echo Открываю Render для деплоя...
    start "" "https://dashboard.render.com"
    echo.
    echo Дальнейшие действия:
    echo 1. На Render нажмите "Manual Deploy"
    echo 2. После деплоя в Telegram нажмите "🔄 Перезагрузить"
    echo.
) else (
    echo.
    echo ОШИБКА загрузки на GitHub!
    echo Возможно, нет изменений для загрузки или проблемы с подключением.
    echo.
)

echo Нажмите любую клавишу для выхода...
pause >nul