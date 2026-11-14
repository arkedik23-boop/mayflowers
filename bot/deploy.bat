@echo off
chcp 65001 >nul
set HOST=root@185.192.246.4
set KEY=%USERPROFILE%\.ssh\morgenshtern_deploy
set OPTS=-i "%KEY%" -o StrictHostKeyChecking=accept-new
cd /d "%~dp0"
echo Загружаю May Flowers на сервер...
ssh %OPTS% %HOST% "mkdir -p /opt/mayflowers_bot"
if errorlevel 1 goto fail
scp %OPTS% bot.py catalog.json .env server_install.sh mayflowers-bot.service %HOST%:/opt/mayflowers_bot/
if errorlevel 1 goto fail
ssh %OPTS% %HOST% "sed -i 's/\r$//' /opt/mayflowers_bot/server_install.sh && bash /opt/mayflowers_bot/server_install.sh"
if errorlevel 1 goto fail
echo.
echo Готово! Напишите боту /start в Telegram.
pause
exit /b 0
:fail
echo.
echo Ошибка. Скопируйте текст выше и пришлите Claude.
pause
exit /b 1
