@echo off
echo ========================================
echo   Telecom AI Call System - Frontend
echo ========================================

cd /d "%~dp0frontend"

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
