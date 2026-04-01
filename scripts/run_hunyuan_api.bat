@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%\hunyuan-upstream"

set "PYTHON=%CD%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Missing upstream venv Python:
  echo   %PYTHON%
  exit /b 1
)

"%PYTHON%" api_server.py --host 127.0.0.1 --port 8080 --model_path tencent/Hunyuan3D-2mini

endlocal
