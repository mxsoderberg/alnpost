@echo off
chcp 65001 >nul
title Публикация материалов

cls
echo ================================
echo    ПУБЛИКАЦИЯ МАТЕРИАЛОВ
echo ================================

cd /d C:\Users\mx\Desktop\sturm\alnpost

echo Проверка файлов в materials...
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

echo Перемещение файлов из materials в wait...
set moved_count=0
for %%f in (materials\*) do (
    if /i not "%%~nxf"==".gitkeep" (
        echo Перемещение: %%~nxf
        move "%%f" "wait\"
        set /a moved_count+=1
    )
)

echo Перемещено %moved_count% файлов.
echo.

echo Загрузка на GitHub...
git add --all
git commit -m "Публикация %date% %time% (%moved_count% файлов)"
git push origin master

if %errorlevel%==0 (
    echo.
    echo УСПЕХ! Файлы перемещены и загружены.
    echo GitHub Actions автоматически запустит деплой.
) else (
    echo ОШИБКА загрузки!
)

pause