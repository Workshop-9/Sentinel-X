@echo off
cd /d "%~dp0"

echo Demarrage de PostgreSQL...
docker compose -f backend\docker-compose.yml up -d --wait
if errorlevel 1 (
    echo Echec du demarrage de PostgreSQL. Verifiez que Docker Desktop est ouvert.
    pause
    exit /b 1
)

echo.
echo API disponible sur http://127.0.0.1:8000/docs
echo Arret avec Ctrl+C.
echo.
"C:\Program Files\Python312\python.exe" -m uvicorn backend.main:app --reload
if errorlevel 1 pause