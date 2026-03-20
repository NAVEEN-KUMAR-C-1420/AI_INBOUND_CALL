@echo off
echo ========================================
echo   MIC Unified Website - Full Start
echo ========================================

echo Starting backend stack...
start "Backend" cmd /k "cd /d %~dp0 && start-backend.bat"

timeout /t 4 /nobreak >nul

echo Starting frontend...
start "Frontend" cmd /k "cd /d %~dp0 && start-frontend.bat"

echo.
echo Services are launching in separate windows.
echo Backend:  http://localhost:8030
echo Frontend: http://localhost:5173 (MIC + integrated theme)
echo Notes: Dashboard / Inbound / Outbound / Analytics are now wired in one site.
echo ========================================
