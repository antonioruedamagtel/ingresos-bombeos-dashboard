@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta primero ABRIR_DASHBOARD.bat para instalar las dependencias.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest tests -q
pause
exit /b %errorlevel%
