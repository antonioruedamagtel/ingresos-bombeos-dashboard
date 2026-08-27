@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo No se ha encontrado Python. Instala Python 3.10 o superior y vuelve a ejecutar este archivo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Primera ejecucion: creando el entorno e instalando dependencias...
  python -m venv .venv
  if errorlevel 1 goto :error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :error
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)

echo.
echo Dashboard disponible en http://127.0.0.1:8050/
echo Mantén esta ventana abierta. Pulsa Ctrl+C para detenerlo.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8050/'"
".venv\Scripts\python.exe" run_dashboard.py
exit /b %errorlevel%

:error
echo.
echo No se ha podido preparar el entorno. Revisa el mensaje anterior.
pause
exit /b 1
