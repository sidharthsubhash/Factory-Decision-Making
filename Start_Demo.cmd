@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=.venv312\Scripts\python.exe"
if not exist "%PYTHON%" (
    py -3.12 -m venv .venv312
    if errorlevel 1 goto :python_required
)
if not exist ".venv312\factory-edge-installed" (
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :install_failed
    type nul > ".venv312\factory-edge-installed"
)
echo.
echo Simulator controls: http://127.0.0.1:8000/simulator
echo Press Ctrl+C to stop the demo.
"%PYTHON%" -m uvicorn src.api:app --host 127.0.0.1 --port 8000
if errorlevel 1 pause
exit /b

:python_required
echo Python 3.12 is required. In PowerShell run:
echo winget install --exact --id Python.Python.3.12
echo Then close this window and run Start_Demo.cmd again.
pause
exit /b 1

:install_failed
echo Dependency installation failed. Check the error above, then run Start_Demo.cmd again.
pause
exit /b 1
