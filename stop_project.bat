@echo off
title Stop LMPC Platform
echo Stopping all running project processes...

taskkill /F /IM uvicorn.exe /T 2>nul
taskkill /F /IM postgres.exe /T 2>nul
taskkill /F /T /FI "WINDOWTITLE eq React Frontend*" 2>nul
taskkill /F /T /FI "WINDOWTITLE eq FastAPI Backend*" 2>nul
taskkill /F /T /FI "WINDOWTITLE eq PostgreSQL Server*" 2>nul

echo All project services stopped.
pause
