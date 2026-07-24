@echo off
REM Launch the actively developed Tauri desktop GUI.
call "%~dp0desktop\run-desktop.bat" %*
exit /b %ERRORLEVEL%
