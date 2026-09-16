@echo off
setlocal EnableDelayedExpansion
title LMPC Compliance Inspector - Full Stack Launcher
echo ========================================================
echo Starting LMPC Compliance Platform...
echo ========================================================

REM -----------------------------------------------------------------------
REM 1. Start Local PostgreSQL 18 on Port 5433
REM    Cluster : backend\db\data_local   (PG_VERSION=18, port=5433)
REM    DB URL  : postgresql://lmpc_app:lmpc_dev_pw@127.0.0.1:5433/lmpc
REM -----------------------------------------------------------------------
echo [1/3] Checking PostgreSQL (Port 5433)...
netstat -ano | findstr ":5433 " >nul 2>&1
if errorlevel 1 (
    echo PostgreSQL not running on port 5433 - starting cluster...

    REM Remove stale PID file if present
    if exist "%~dp0backend\db\data_local\postmaster.pid" (
        del /f /q "%~dp0backend\db\data_local\postmaster.pid" 2>nul
    )

    REM Resolve pg_ctl.exe - prefer PG18 binary which matches the cluster
    set "PGCTL="
    if exist "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" set "PGCTL=C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
    if not defined PGCTL if exist "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" set "PGCTL=C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe"
    if not defined PGCTL if exist "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" set "PGCTL=C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe"
    if not defined PGCTL (
        for /f "delims=" %%I in ('where pg_ctl 2^>nul') do (
            if not defined PGCTL set "PGCTL=%%I"
        )
    )

    if defined PGCTL (
        echo Starting PostgreSQL cluster using: !PGCTL!
        "%PGCTL%" start -D "%~dp0backend\db\data_local" -o "-p 5433" -l "%~dp0backend\db\data_local\logfile.txt" -s -w
        if errorlevel 1 (
            echo [ERROR] pg_ctl failed to start PostgreSQL. Check logfile:
            echo         %~dp0backend\db\data_local\logfile.txt
            pause
            exit /b 1
        )
        echo PostgreSQL started successfully on port 5433.
        timeout /t 2 /nobreak >nul
    ) else (
        echo [ERROR] pg_ctl.exe not found. Install PostgreSQL 18 and ensure it is in PATH.
        pause
        exit /b 1
    )
) else (
    echo PostgreSQL is already running on port 5433.
)

REM -----------------------------------------------------------------------
REM 2. Start FastAPI Backend on Port 8000
REM    Uses backend\.env  ->  DATABASE_URL=postgresql://...@127.0.0.1:5433/lmpc
REM -----------------------------------------------------------------------
echo [2/3] Starting FastAPI Backend (Port 8000)...
start "FastAPI Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload"

REM Give the backend a moment to initialise before opening browser
timeout /t 4 /nobreak >nul

REM -----------------------------------------------------------------------
REM 3. Start React Frontend Dev Server on Port 5173
REM -----------------------------------------------------------------------
echo [3/3] Starting React Frontend (Port 5173)...
start "React Frontend" cmd /k "cd /d %~dp0frontend\react-app && npm run dev"

timeout /t 3 /nobreak >nul

echo ========================================================
echo ALL SERVICES ARE UP AND RUNNING!
echo ========================================================
echo App URL:     http://localhost:5173
echo Backend API: http://localhost:8000/docs
echo Health:      http://localhost:8000/health
echo Username:    admin
echo Password:    password123
echo.
echo DB Host:     127.0.0.1
echo DB Port:     5433
echo DB Name:     lmpc
echo DB User:     lmpc_app
echo ========================================================

REM IMPORTANT: start requires an empty title string before a URL.
REM Without "", cmd.exe treats the URL as the window title and
REM tries to execute "//localhost:5173" as a command (the 'art' error).
start "" "http://localhost:5173"

pause
endlocal
