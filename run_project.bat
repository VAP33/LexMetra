@echo off
setlocal EnableDelayedExpansion
title LexMetra Compliance Inspector - Full Stack Launcher

echo ===============================================================================
echo                LEXMETRA UNIFIED COMPLIANCE INSPECTION PLATFORM
echo ===============================================================================
echo Active Subsystems:
echo   [*] Semantic Authority    : Qwen 3.8 27B (Multimodal Perception Pipeline)
echo   [*] Evidence Localization : Sanskruti CV (PaddleOCR PP-OCRv6 Vector Polygons)
echo   [*] Regulatory Engine     : Arya Generic Engine (IN-LMPC-2011:2011-consolidated)
echo   [*] Multi-Panel DB        : PostgreSQL 18 Local Cluster (Port 5433)
echo   [*] Interactive Web UI    : React 18 + Vite + SVG Polygon Overlays (Port 5173)
echo ===============================================================================
echo.

REM -------------------------------------------------------------------------------
REM Environment Configuration (Enforce Sanskruti + Arya Generic Modes)
REM -------------------------------------------------------------------------------
set "EVIDENCE_LOCALIZER_MODE=sanskruti"
set "REGULATORY_ENGINE_MODE=generic"
set "LMPC_ENABLE_PADDLEOCR=true"
set "ENABLE_LOCALIZATION_YOLO=false"
set "OPENROUTER_MODEL=qwen/qwen3.8-27b"

REM -------------------------------------------------------------------------------
REM 1. Check & Start Local PostgreSQL 18 on Port 5433
REM -------------------------------------------------------------------------------
echo [1/3] Checking PostgreSQL Database (Port 5433)...
netstat -ano | findstr ":5433 " >nul 2>&1
if errorlevel 1 (
    echo [!] PostgreSQL not running on port 5433. Starting cluster...

    if exist "%~dp0backend\db\data_local\postmaster.pid" (
        del /f /q "%~dp0backend\db\data_local\postmaster.pid" 2>nul
    )

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
        set "PGCTL=!PGCTL:"=!"
        echo     Using pg_ctl: "!PGCTL!"
        "!PGCTL!" start -D "%~dp0backend\db\data_local" -o "-p 5433" -l "%~dp0backend\db\data_local\logfile.txt" -s -w
        if errorlevel 1 (
            echo [ERROR] pg_ctl failed to start PostgreSQL. Check logfile:
            echo         %~dp0backend\db\data_local\logfile.txt
            pause
            exit /b 1
        )
        echo [OK] PostgreSQL cluster started successfully on port 5433.
        timeout /t 2 /nobreak >nul
    ) else (
        echo [ERROR] pg_ctl.exe not found. Ensure PostgreSQL 18 is installed.
        pause
        exit /b 1
    )
) else (
    echo [OK] PostgreSQL is already active on port 5433.
)

REM -------------------------------------------------------------------------------
REM 2. Check & Start FastAPI Backend on Port 8000
REM -------------------------------------------------------------------------------
echo.
echo [2/3] Checking FastAPI Backend Service (Port 8000)...
netstat -ano | findstr ":8000 " >nul 2>&1
if errorlevel 1 (
    echo [!] Backend not running on port 8000. Launching with Sanskruti + Arya modes...
    start "LexMetra Backend - Sanskruti + Arya" cmd /k "cd /d %~dp0backend && set EVIDENCE_LOCALIZER_MODE=sanskruti&& set REGULATORY_ENGINE_MODE=generic&& set LMPC_ENABLE_PADDLEOCR=true&& set ENABLE_LOCALIZATION_YOLO=false&& python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload"
    timeout /t 4 /nobreak >nul
    echo [OK] FastAPI Backend process initiated.
) else (
    echo [OK] FastAPI Backend is already active on port 8000.
)

REM -------------------------------------------------------------------------------
REM 3. Check & Start React Frontend on Port 5173
REM -------------------------------------------------------------------------------
echo.
echo [3/3] Checking React Frontend Dev Server (Port 5173)...
netstat -ano | findstr ":5173 " >nul 2>&1
if errorlevel 1 (
    echo [!] Frontend not running on port 5173. Launching Vite dev server...
    start "LexMetra Frontend - React Vite" cmd /k "cd /d %~dp0frontend\react-app && npm run dev"
    timeout /t 3 /nobreak >nul
    echo [OK] React Frontend process initiated.
) else (
    echo [OK] React Frontend is already active on port 5173.
)

echo.
echo ===============================================================================
echo                     ALL LEXMETRA SERVICES ARE ONLINE!
echo ===============================================================================
echo  Application Web UI : http://localhost:5173
echo  FastAPI Docs / API : http://localhost:8000/docs
echo  Health Endpoint    : http://localhost:8000/health
echo.
echo  Default Inspector Credentials:
echo    Username : admin
echo    Password : password123
echo.
echo  Active Integration Subsystems:
echo    [+] Evidence Localizer : sanskruti (PaddleOCR tight vector polygons)
echo    [+] Regulatory Engine  : generic (Arya IN-LMPC-2011 Ruleset Report)
echo    [+] Semantic Provider  : Qwen 3.8-27B (multimodal OpenRouter inference)
echo ===============================================================================
echo.

REM Open Web Application in Default Browser
start "" "http://localhost:5173"

echo Press any key to exit this launcher window (services will continue running)...
pause >nul
endlocal
