@echo off
REM Compatibility wrapper. The maintained launcher lives in desktop\run.bat.
call "%~dp0desktop\run.bat" %*
exit /b %ERRORLEVEL%
