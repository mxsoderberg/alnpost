@echo off
chcp 65001 >nul
title Публикация материалов

cls
echo ================================
echo    ПУБЛИКАЦИЯ МАТЕРИАЛОВ
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

echo Загрузка на GitHub...
git add --all
git commit -m "Публикация %date% %time% (%count% файлов)"
git push origin master

if %errorlevel%==0 (
    echo.
    echo УСПЕХ! Файлы загружены.
    echo GitHub Actions автоматически запустит деплой.
) else (
    echo ОШИБКА загрузки!
)

pause