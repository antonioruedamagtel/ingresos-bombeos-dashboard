@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Necesitas Python 3 para abrir la demo localmente.
  pause
  exit /b 1
)

echo.
echo Dashboard HTML disponible en http://127.0.0.1:8051/
echo Manten esta ventana abierta. Pulsa Ctrl+C para detenerlo.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8051/'"
python -m http.server 8051 --bind 127.0.0.1
