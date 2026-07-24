@echo off
REM Modern auvide desktop launcher. It prepares local frontend dependencies and
REM lets Tauri stage the engine and verified uv sidecar before opening the GUI.
setlocal EnableExtensions
set "DESKTOP_DIR=%~dp0"
pushd "%DESKTOP_DIR%" >nul

where bun >nul 2>&1
if errorlevel 1 (
  echo [error] Bun was not found on PATH. Install it from https://bun.sh and try again.
  goto :fail
)

where cargo >nul 2>&1
if errorlevel 1 (
  echo [error] Rust/Cargo was not found on PATH. Install Rust from https://rustup.rs and try again.
  goto :fail
)

where uv >nul 2>&1
if errorlevel 1 (
  echo [error] uv was not found on PATH. Install it with: winget install --id astral-sh.uv
  echo         The managed runtime bootstrap is still being integrated; the current GUI needs uv for renders.
  goto :fail
)

if not exist "node_modules\@tauri-apps\cli" (
  echo [auvide] Installing desktop dependencies...
  call bun install --frozen-lockfile
  if errorlevel 1 goto :fail
)

if /i "%~1"=="--check" (
  echo [auvide] Desktop development prerequisites are ready.
  popd >nul
  exit /b 0
)

echo [auvide] Starting the desktop GUI...
call bun run tauri dev
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%

:fail
popd >nul
pause
exit /b 1
