@echo off
chcp 65001 >nul
title Обновление кода бота

cls
echo Обновление кода бота...
cd /d C:\Users\mx\Desktop\sturm\alnpost

git add alnbot.py
git commit -m "Обновление кода %date% %time%"
git push origin master

if %errorlevel%==0 (
    echo Код обновлен! Открытие Render...
    start "" "https://dashboard.render.com"
) else (
    echo Ошибка обновления кода!
)

pause