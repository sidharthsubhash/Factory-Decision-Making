@echo off
setlocal
cd /d "%~dp0"
set "BROKER=%ProgramFiles%\mosquitto\mosquitto.exe"
if exist "%BROKER%" goto start
where mosquitto.exe >nul 2>&1
if errorlevel 1 (
    echo Mosquitto is required for the optional MQTT demonstration.
    exit /b 1
)
set "BROKER=mosquitto.exe"
:start
"%BROKER%" -c "config\mosquitto-local.conf" -v
exit /b %errorlevel%
