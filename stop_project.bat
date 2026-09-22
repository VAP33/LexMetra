@echo off
title Stop LMPC Platform
echo Stopping all running project processes...

REM Stop Vite frontend and FastAPI backend
taskkill /F /IM uvicorn.exe /T 2>nul
taskkill /F /T /FI "WINDOWTITLE eq LexMetra Frontend*" 2>nul
taskkill /F /T /FI "WINDOWTITLE eq LexMetra Backend*" 2>nul
taskkill /F /T /FI "WINDOWTITLE eq React Frontend*" 2>nul
taskkill /F /T /FI "WINDOWTITLE eq FastAPI Backend*" 2>nul

REM Stop dedicated local PostgreSQL cluster gracefully without affecting system service
if exist "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" (
    "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" stop -D "%~dp0backend\db\data_local" -m fast 2>nul
)
taskkill /F /T /FI "WINDOWTITLE eq LexMetra PostgreSQL*" 2>nul
taskkill /F /T /FI "WINDOWTITLE eq PostgreSQL Server*" 2>nul

echo All project services stopped.
pause
