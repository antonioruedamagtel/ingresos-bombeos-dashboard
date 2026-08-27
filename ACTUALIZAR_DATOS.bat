@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta primero ABRIR_DASHBOARD.bat para instalar las dependencias.
  pause
  exit /b 1
)
if not exist ".env" (
  echo Falta el fichero .env con ESIOS_API_KEY. Copia .env.example a .env y añade tu token.
  pause
  exit /b 1
)

set /p IB_START=Fecha inicial [AAAA-MM-DD]: 
set /p IB_END=Fecha final [AAAA-MM-DD]: 
if "%IB_START%"=="" goto :missing
if "%IB_END%"=="" goto :missing

".venv\Scripts\python.exe" cli.py ingest --start %IB_START% --end %IB_END%
if errorlevel 1 goto :error
".venv\Scripts\python.exe" cli.py build --start %IB_START% --end %IB_END%
if errorlevel 1 goto :error
".venv\Scripts\python.exe" cli.py qa --start %IB_START% --end %IB_END%
if errorlevel 1 goto :error

echo.
echo Actualizacion y controles terminados. Reinicia el dashboard para ver los datos.
pause
exit /b 0

:missing
echo Debes indicar las dos fechas.
pause
exit /b 1

:error
echo.
echo La actualizacion se ha detenido. Revisa el mensaje anterior; los datos ya validados se conservan.
pause
exit /b 1
