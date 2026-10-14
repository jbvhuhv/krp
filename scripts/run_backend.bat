@echo off
setlocal
REM ============================================================
REM  KRP - start backend (portable)
REM  1) locate repo by this script's own path
REM  2) detect Python (PYTHON_CMD -> py -> python)
REM  3) ensure logs\ exists, then start uvicorn
REM  Override interpreter with: set PYTHON_CMD=...
REM ============================================================
set "ROOT=%~dp0.."
set "BACKEND=%ROOT%\backend"

set "PYTHON="
if defined PYTHON_CMD set "PYTHON=%PYTHON_CMD%"
if not defined PYTHON (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON=py"
)
if not defined PYTHON (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
  echo [ERROR] Python 3.12+ not found. Install it, or set PYTHON_CMD, then retry.
  exit /b 1
)

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [OK] Python : %PYTHON%
echo [OK] Backend: %BACKEND%
echo [OK] Logs   : %ROOT%\logs\be_out.log

cd /d "%BACKEND%"
"%PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> "%ROOT%\logs\be_out.log" 2>> "%ROOT%\logs\be_err.log"
endlocal
