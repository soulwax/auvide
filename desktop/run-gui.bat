@echo off
REM auvide legacy Tkinter GUI launcher. Uses uv to provide Python + tkinter
REM (no system Python needed) and installs the auvide engine from ../engine.
setlocal
where uv >nul 2>&1
if errorlevel 1 (
  echo [error] uv was not found on PATH. Install uv, or run:
  echo         pip install ..\engine pillow ^&^& python "%~dp0legacy\gui.py"
  pause
  exit /b 1
)
uv run --python 3.12 --with "%~dp0..\engine" --with pillow "%~dp0legacy\gui.py" %*
if errorlevel 1 pause
