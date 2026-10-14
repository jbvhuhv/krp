@echo off
setlocal

REM ============================================================
REM  KRP - one-click environment setup (Windows)
REM  1) locate Python / Node
REM  2) install backend (pip) and frontend (npm) dependencies
REM  3) create backend\.env from .env.example when missing
REM  4) print Neo4j startup hints
REM  Override the interpreter with: set PYTHON_CMD=...
REM ============================================================

set "ROOT=%~dp0.."
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"

echo === KRP one-click setup ===

REM ---------- locate Python ----------
set "PYTHON="
if defined PYTHON_CMD set "PYTHON=%PYTHON_CMD%"
if not defined PYTHON if exist "D:\Python313\python.exe" set "PYTHON=D:\Python313\python.exe"
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
echo [OK] Python: %PYTHON%

REM ---------- locate Node / npm ----------
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js / npm not found. Install Node 18+ then retry.
  exit /b 1
)
echo [OK] npm found.

REM ---------- backend dependencies ----------
echo [1/4] Installing backend requirements ...
pushd "%BACKEND%"
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] backend dependency installation failed.
  popd
  exit /b 1
)
popd

REM ---------- backend .env ----------
echo [2/4] Preparing backend\.env ...
if not exist "%BACKEND%\.env" (
  copy /y "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
  echo [OK] created backend\.env from .env.example - fill in your API keys.
) else (
  echo [SKIP] backend\.env already exists.
)

REM ---------- frontend dependencies ----------
echo [3/4] Installing frontend dependencies ...
pushd "%FRONTEND%"
call npm install
if errorlevel 1 (
  echo [ERROR] npm install failed.
  popd
  exit /b 1
)
popd

REM ---------- Neo4j reminder ----------
echo [4/4] Neo4j is required. Start it with Docker:
echo    docker : docker compose up -d neo4j        (先在仓库根目录建 .env 并写入 NEO4J_PASSWORD)
echo    local  : 方式二需自备 JDK 21 与 Neo4j 构建产物（deps/ 未随仓库分发）

echo.
echo === setup finished ===
echo   backend : scripts\run_backend.bat
echo   frontend: cd frontend ^&^& npm run dev
endlocal
exit /b 0