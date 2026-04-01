@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"

python -m uvicorn app:app --host 127.0.0.1 --port 7861

endlocal
