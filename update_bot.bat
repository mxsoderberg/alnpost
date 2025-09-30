@echo off
chcp 65001 >nul
title Обновление кода бота

cls
echo ================================
echo    ОБНОВЛЕНИЕ КОДА БОТА
echo ================================

cd /d C:\Users\mx\Desktop\sturm\alnpost

echo Обновление кода бота...
git add alnbot.py
git commit -m "Обновление кода %date% %time%"
git push origin master

if %errorlevel%==0 (
    echo.
    echo УСПЕХ! Код обновлен.
    echo GitHub Actions автоматически запустит деплой.
) else (
    echo ОШИБКА обновления кода!
)

pause