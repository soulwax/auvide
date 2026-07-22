@echo off
REM auvide launcher - forwards all args to the auvide CLI engine.
REM   double-clickable: drag a video file onto this .bat to upscale with defaults
setlocal
where uv >nul 2>&1
if errorlevel 1 (
  echo [error] uv was not found on PATH. Install uv (https://astral.sh/uv), or
  echo         pip install ..\engine and run: python -m auvide.cli
  pause
  exit /b 1
)
uv run --python 3.12 --project "%~dp0..\engine" -m auvide.cli %*
if errorlevel 1 pause
