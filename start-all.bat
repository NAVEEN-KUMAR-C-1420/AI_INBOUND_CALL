@echo off
echo ========================================
echo   Telecom AI Call System - Full Start
echo ========================================

echo Starting backend stack...
start "Backend" cmd /k "cd /d %~dp0 && start-backend.bat"

timeout /t 4 /nobreak >nul

echo Starting frontend...
start "Frontend" cmd /k "cd /d %~dp0 && start-frontend.bat"

echo.
echo Services are launching in separate windows.
echo Backend:  http://localhost:8030
echo Frontend: http://localhost:5173 (fixed; startup fails if busy)
echo ========================================
