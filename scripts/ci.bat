@echo off
setlocal
REM ============================================================
REM  KRP - local CI (portable): ruff -> pytest -> eslint -> build
REM  Locates the repo by this script's own path; detects Python.
REM  Requires: pip install -r backend/requirements-dev.txt (ruff)
REM  Override interpreter with: set PYTHON_CMD=...
REM ============================================================
set "ROOT=%~dp0.."

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

echo === [1/4] Backend lint (ruff) ===
pushd "%ROOT%\backend"
"%PYTHON%" -m ruff --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] ruff is not installed. Run: pip install -r backend/requirements-dev.txt
  popd
  exit /b 1
)
"%PYTHON%" -m ruff check app
if errorlevel 1 (
  echo BACKEND LINT FAILED
  popd
  exit /b 1
)
popd

echo === [2/4] Backend tests ===
pushd "%ROOT%\backend"
"%PYTHON%" -m pytest -q
if errorlevel 1 (
  echo BACKEND TESTS FAILED
  popd
  exit /b 1
)
popd

echo === [3/4] Frontend lint (eslint) ===
pushd "%ROOT%\frontend"
call npm run lint
if errorlevel 1 (
  echo FRONTEND LINT FAILED
  popd
  exit /b 1
)
popd

echo === [4/4] Frontend build ===
pushd "%ROOT%\frontend"
call npm run build
if errorlevel 1 (
  echo FRONTEND BUILD FAILED
  popd
  exit /b 1
)
popd

echo === CI OK ===
endlocal
exit /b 0
