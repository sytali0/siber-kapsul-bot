@echo off
chcp 65001 >nul
title InstaTech Otomasyon Sistemi
cd /d "%~dp0"
echo ========================================================
echo   InstaTech Otomasyon Sistemi Baslatiliyor...
echo   Kontrol Paneli: http://localhost:8000
echo ========================================================
start "" http://localhost:8000
".venv\Scripts\python.exe" -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
