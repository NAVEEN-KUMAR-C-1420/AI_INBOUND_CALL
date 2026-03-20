@echo off
echo ========================================
echo   Telecom AI Call System - Backend
echo ========================================

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

echo Checking for Python virtual environment...
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Upgrading pip tooling in backend venv...
venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

echo Installing dependencies...
venv\Scripts\python.exe -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo Dependency install failed. Backend will not start.
    exit /b 1
)

echo.
echo Starting FastAPI server on http://localhost:8020
echo ========================================
venv\Scripts\python.exe -m uvicorn main:app --app-dir "%~dp0backend" --host 0.0.0.0 --port 8020 --reload
