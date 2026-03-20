@echo off
echo ========================================
echo   Telecom AI Call System - Frontend
echo ========================================

cd /d "%~dp0frontend"

echo Checking frontend port 5173...
netstat -ano | findstr ":5173" >nul
if %errorlevel% equ 0 (
    echo ERROR: Port 5173 is already in use. Stop existing frontend process first.
    exit /b 1
)

echo Checking for node_modules...
if not exist "node_modules" (
    echo Installing dependencies...
    npm install
)

echo.
echo Starting React development server...
echo Open http://localhost:5173 in your browser
echo ========================================
npm run dev
