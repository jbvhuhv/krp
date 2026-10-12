@echo off
setlocal
if not defined PYTHON set "PYTHON=D:\Python313\python.exe"

echo === [1/4] Backend lint (ruff) ===
pushd "%~dp0..\backend"
"%PYTHON%" -m ruff check app
if errorlevel 1 (
  echo BACKEND LINT FAILED
  popd
  exit /b 1
)
popd

echo === [2/4] Backend tests ===
pushd "%~dp0..\backend"
"%PYTHON%" -m pytest -q
if errorlevel 1 (
  echo BACKEND TESTS FAILED
  popd
  exit /b 1
)
popd

echo === [3/4] Frontend lint (eslint) ===
pushd "%~dp0..\frontend"
call npm run lint
if errorlevel 1 (
  echo FRONTEND LINT FAILED
  popd
  exit /b 1
)
popd

echo === [4/4] Frontend build ===
pushd "%~dp0..\frontend"
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