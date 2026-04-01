@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo Running first-time Hunyuan bootstrap...
powershell -ExecutionPolicy Bypass -File "%ROOT%scripts\setup_hunyuan.ps1" -PythonSelector "python"
if errorlevel 1 (
  echo.
  echo Bootstrap failed. Review the output above.
  pause
  exit /b 1
)

echo.
echo Bootstrap succeeded. Starting services...
call "%ROOT%start_hunyuan_launcher.bat"

endlocal
