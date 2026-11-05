@echo off
setlocal
REM ============================================================
REM  KRP - start the bundled local Neo4j (Windows)
REM  1) locate repo by this script's own path
REM  2) detect Java (JAVA_CMD -> deps\jdk21\* -> PATH)
REM  3) start deps\neo4j-build via CommunityEntryPoint (foreground)
REM  Override interpreter with: set JAVA_CMD=D:\path\to\java.exe
REM
REM  NOTE: deps\ is a build artefact kept only on the author's dev machine
REM  (excluded by .gitignore /deps/). It ships no official bin\ scripts,
REM  so `neo4j start` does not work - we launch the JVM directly.
REM  Fresh clones have no deps\: use Docker instead -> docker compose up -d neo4j
REM
REM  This file is intentionally ASCII-only: cmd.exe parses .bat as ANSI,
REM  and UTF-8 Chinese text corrupts the following lines.
REM ============================================================
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "NEO4J_HOME=%ROOT%\deps\neo4j-build"
set "TARGET=%NEO4J_HOME%\target"
set "LOG=%ROOT%\logs\neo4j.log"

if not exist "%TARGET%\lib" (
  echo [ERROR] local Neo4j runtime not found: %TARGET%\lib
  echo         deps\ is not shipped with the repo ^(.gitignore /deps/^).
  echo         Use Docker instead: docker compose up -d neo4j
  exit /b 1
)
if not exist "%TARGET%\conf\neo4j.conf" (
  echo [ERROR] missing config: %TARGET%\conf\neo4j.conf
  exit /b 1
)

set "JAVA="
if defined JAVA_CMD set "JAVA=%JAVA_CMD%"
if not defined JAVA if exist "%ROOT%\deps\jdk21" (
  for /d %%D in ("%ROOT%\deps\jdk21\*") do (
    if not defined JAVA if exist "%%~fD\bin\java.exe" set "JAVA=%%~fD\bin\java.exe"
  )
)
if not defined JAVA (
  where java >nul 2>nul
  if not errorlevel 1 set "JAVA=java"
)
if not defined JAVA (
  echo [ERROR] Java 17+ not found. Install a JDK, or set JAVA_CMD, then retry.
  exit /b 1
)

netstat -ano | findstr ":7687" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo [SKIP] Bolt 7687 is already listening - Neo4j looks up.
  echo        To restart, stop the java process holding 7687 first.
  exit /b 0
)

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [OK] Java : %JAVA%
echo [OK] Home : %TARGET%
echo [OK] Logs : %LOG%
echo [OK] Bolt : 7687 / HTTP : 7474
echo [..] starting in foreground, press Ctrl+C to stop
echo      local conf has auth disabled (dbms.security.auth_enabled=false)
echo.

cd /d "%NEO4J_HOME%"
"%JAVA%" -cp "target\lib\*" org.neo4j.server.CommunityEntryPoint --home-dir=target --config-dir=target\conf >> "%LOG%" 2>&1
endlocal
