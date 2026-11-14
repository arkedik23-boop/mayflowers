@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "IP=185.192.246.4"
set "KEY=%USERPROFILE%\.ssh\morgenshtern_deploy"
set SSHOPT=-i "%KEY%" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new
echo ============================================
echo   May Flowers: установка бота на сервер %IP%
echo ============================================
where ssh >nul 2>nul
if errorlevel 1 goto fail
if not exist "%KEY%" goto nokey
if not exist ".env" goto fail
echo Копирую файлы...
ssh %SSHOPT% root@%IP% "mkdir -p /opt/mayflowers_bot"
if errorlevel 1 goto fail
scp %SSHOPT% bot.py catalog.json .env server_install.sh mayflowers-bot.service root@%IP%:/opt/mayflowers_bot/
if errorlevel 1 goto fail
echo Устанавливаю...
ssh %SSHOPT% root@%IP% "sed -i 's/\r$//' /opt/mayflowers_bot/server_install.sh && bash /opt/mayflowers_bot/server_install.sh"
if errorlevel 1 goto fail
echo.
echo Готово! Напишите боту /start в Telegram.
pause
exit /b 0
:nokey
echo Не найден ключ доступа morgenshtern_deploy. Сначала запустите deploy.bat бота Моргенштерна.
pause
exit /b 1
:fail
echo.
echo Ошибка. Сфотографируйте это окно и пришлите Claude.
pause
exit /b 1
