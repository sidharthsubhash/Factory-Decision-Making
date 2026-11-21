@echo off
setlocal
cd /d "%~dp0node_red"
where npm >nul 2>&1
if errorlevel 1 (
    echo Install Node.js LTS and reopen this window.
    pause
    exit /b 1
)
if not exist "node_modules\.bin\node-red.cmd" (
    call npm ci --no-audit --no-fund
    if errorlevel 1 (
        echo Node-RED installation failed. Review the error above and try again.
        pause
        exit /b 1
    )
)
echo Dashboard: http://127.0.0.1:1880/edge-live/compressor
call node_modules\.bin\node-red.cmd --userDir "%CD%" --settings "%CD%\settings.js"
if errorlevel 1 pause
