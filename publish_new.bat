@echo off
chcp 65001 >nul
title Публикация новых материалов

cls
echo ================================
echo    ПУБЛИКАЦИЯ НОВЫХ МАТЕРИАЛОВ
echo ================================

cd /d C:\Users\mx\Desktop\sturm\alnpost

echo Проверка новых файлов в materials...
set new_count=0
set moved_count=0

:: Подсчитываем количество файлов в materials (кроме .gitkeep)
for %%f in (materials\*) do (
    if /i not "%%~nxf"==".gitkeep" (
        set /a new_count+=1
    )
)

if %new_count%==0 (
    echo Нет новых файлов для публикации!
    pause
    exit /b
)

echo Найдено %new_count% новых файлов.
echo.

echo Перемещение новых файлов из materials в wait...
:: Перемещаем все файлы из materials в wait
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
git commit -m "Добавлены новые материалы %date% %time% (%moved_count% файлов)"
git push origin master

if %errorlevel%==0 (
    echo.
    echo УСПЕХ! Новые файлы перемещены и загружены.
    echo Старые файлы в wait сохранены.
    echo GitHub Actions автоматически запустит деплой.
) else (
    echo ОШИБКА загрузки!
)

pause