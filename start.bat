@echo off
echo ========================================================
echo   Starting Enterprise Offline AI RAG Platform
echo ========================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Check if Node.js is installed
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH.
    pause
    exit /b 1
)

echo Starting FastAPI Backend...
start "RAG Backend" cmd /k "cd backend && python -m uvicorn main:app --app-dir . --reload --host 0.0.0.0 --port 30000"

echo Starting React Frontend...
start "RAG Frontend" cmd /k "cd frontend && npm run dev -- --host 0.0.0.0 --port 30001"

echo.
echo Application started!
echo Backend API  : http://localhost:30000/api/docs
echo Web Interface: http://localhost:30001
echo LAN Access   : http://192.168.0.127:30001
echo.
