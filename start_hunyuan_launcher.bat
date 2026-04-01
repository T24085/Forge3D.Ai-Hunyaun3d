@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "LAUNCHER_PY=python"
set "LAUNCHER_PORT=7861"
set "HUNYUAN_HOST=127.0.0.1"
set "HUNYUAN_PORT=8080"
set "UPSTREAM_DIR=%ROOT%hunyuan-upstream"
set "UPSTREAM_PY=%UPSTREAM_DIR%\.venv\Scripts\python.exe"

if not exist "%UPSTREAM_DIR%\api_server.py" (
  echo Hunyuan upstream repo not found at:
  echo   %UPSTREAM_DIR%
  echo.
  echo Clone/bootstrap is incomplete. Current project expects the official repo in "hunyuan-upstream".
  pause
  exit /b 1
)

if not exist "%UPSTREAM_PY%" (
  echo Upstream virtual environment not found at:
  echo   %UPSTREAM_PY%
  echo.
  echo Run this first:
  echo   powershell -ExecutionPolicy Bypass -File "%ROOT%scripts\setup_hunyuan.ps1"
  echo.
  pause
  exit /b 1
)

echo Starting Hunyuan API on %HUNYUAN_HOST%:%HUNYUAN_PORT% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath '%UPSTREAM_PY%' -WorkingDirectory '%UPSTREAM_DIR%' -ArgumentList 'api_server.py','--host','%HUNYUAN_HOST%','--port','%HUNYUAN_PORT%','--model_path','tencent/Hunyuan3D-2mini'"

echo Waiting for Hunyuan API background process to initialize ...
timeout /t 6 /nobreak >nul

echo Starting launcher UI on http://127.0.0.1:%LAUNCHER_PORT% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'python' -WorkingDirectory '%ROOT%' -ArgumentList '-m','uvicorn','app:app','--host','127.0.0.1','--port','%LAUNCHER_PORT%'"

timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:%LAUNCHER_PORT%"

echo.
echo Started:
echo   Hunyuan API:      http://%HUNYUAN_HOST%:%HUNYUAN_PORT%
echo   Launcher UI:      http://127.0.0.1:%LAUNCHER_PORT%
echo.
echo Processes are running hidden in the background.
echo First launch may take several minutes while Hunyuan loads or downloads weights.
echo Use the website Exit button to stop services cleanly.
endlocal
