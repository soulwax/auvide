@echo off
REM Compatibility wrapper. The maintained legacy launcher lives in desktop\run-gui.bat.
call "%~dp0desktop\run-gui.bat" %*
exit /b %ERRORLEVEL%
