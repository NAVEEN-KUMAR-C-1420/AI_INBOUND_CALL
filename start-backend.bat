@echo off
echo ========================================
echo   Telecom AI Call System - Backend
echo ========================================

echo Checking backend port 8030...
netstat -ano | findstr ":8030" >nul
if %errorlevel% equ 0 (
    echo ERROR: Port 8030 is already in use. Stop existing backend process first.
    exit /b 1
)

echo Checking Ollama on port 11434...
netstat -ano | findstr ":11434" >nul
if %errorlevel% neq 0 (
    echo Starting Ollama...
    start "" ollama serve
    timeout /t 5 /nobreak >nul
) else (
    echo Ollama already running.
)

cd /d "%~dp0backend"

echo Checking for Python virtual environment in project root (.venv)...
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Creating virtual environment...
    cd /d "%~dp0"
    python -m venv .venv
    cd /d "%~dp0backend"
)

echo Activating virtual environment...
call "%~dp0.venv\Scripts\activate"

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Starting FastAPI server on http://localhost:8030
echo ========================================
python -m uvicorn main:app --host 0.0.0.0 --port 8030 --reload
