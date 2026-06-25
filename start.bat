@echo off
echo ============================================================
echo   Telecom AI Call System - Unified Startup
echo ============================================================

:: 1. Check ports
echo Checking ports...
netstat -ano | findstr ":8030" >nul
if %errorlevel% equ 0 (
    echo WARNING: Port 8030 is already in use. Ensure no old backend instance is running.
)

netstat -ano | findstr ":5173" >nul
if %errorlevel% equ 0 (
    echo WARNING: Port 5173 is already in use. Ensure no old frontend instance is running.
)

:: 2. Check and start Ollama
echo Checking Ollama on port 11434...
netstat -ano | findstr ":11434" >nul
if %errorlevel% neq 0 (
    echo Starting Ollama...
    start "" ollama serve
    timeout /t 5 /nobreak >nul
) else (
    echo Ollama is already running.
)

:: 3. Start Backend in a separate window
echo Starting backend server on http://localhost:8030 ...
start "Call System Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8030 --reload"

:: 4. Start Frontend in a separate window
echo Starting React frontend on http://localhost:5173 ...
start "Call System Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo ============================================================
echo   Services launched in separate windows!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8030
echo ============================================================
