@echo off
title LMPC Compliance Inspector - Full Stack Launcher
echo ========================================================
echo Starting LMPC Compliance Platform...
echo ========================================================

REM 1. Start Local PostgreSQL on Port 5433
echo [1/3] Checking PostgreSQL (Port 5433)...
if exist "%~dp0backend\db\data_local\postmaster.pid" (
    netstat -ano | findstr :5433 >nul
    if errorlevel 1 del /f /q "%~dp0backend\db\data_local\postmaster.pid" 2>nul
)
netstat -ano | findstr :5433 >nul
if errorlevel 1 (
    echo Starting PostgreSQL Server...
    start "PostgreSQL Server" /min "C:\Program Files\PostgreSQL\18\bin\postgres.exe" -D "%~dp0backend\db\data_local" -p 5433
    timeout /t 2 /nobreak >nul
) else (
    echo PostgreSQL is already running on port 5433.
)

REM 2. Start FastAPI Backend on Port 8000
echo [2/3] Starting FastAPI Backend (Port 8000)...
start "FastAPI Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000"

REM 3. Start Frontend React Dev Server on Port 5173
echo [3/3] Starting React Frontend (Port 5173)...
start "React Frontend" cmd /k "cd /d %~dp0frontend\react-app && npm run dev"

timeout /t 3 /nobreak >nul

echo ========================================================
echo ALL SERVICES ARE UP AND RUNNING!
echo ========================================================
echo App URL:     http://localhost:5173
echo Backend API: http://localhost:8000/docs
echo Username:    admin
echo Password:    password123
echo ========================================================
start http://localhost:5173
pause
