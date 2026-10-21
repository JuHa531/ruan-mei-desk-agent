@echo off
rem ============================================================
rem  Mei Mei - local AI agent launcher (console / debug mode)
rem  Double-click this file. Everything else is handled for you.
rem  (Keep this file ASCII-only: cmd.exe reads .bat before the
rem   codepage is switched, so non-ASCII here would garble.)
rem
rem  WORKDIR = the folder the agent is allowed to touch.
rem  Change the line below if you want it to work somewhere else.
rem ============================================================
title Mei Mei - closing this window stops the app
cd /d "%~dp0"

set "WORKDIR=%USERPROFILE%\Documents\rm-workspace"
if not exist "%WORKDIR%" mkdir "%WORKDIR%"

echo.
echo   Starting local AI service, please wait...
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0启动语音.ps1"

rem If the app is already running, just open the browser.
powershell -NoProfile -Command "exit [int](-not [bool](Get-NetTCPConnection -LocalPort 7788 -State Listen -ErrorAction SilentlyContinue))"
if errorlevel 1 goto launch

echo.
echo   App is already running - opening browser.
start "" "http://127.0.0.1:7788"
timeout /t 3 >nul
goto :eof

:launch
echo.
echo   Starting agent app on http://127.0.0.1:7788
echo   Work folder: %WORKDIR%
echo   (the browser should open automatically)
echo.

"D:\ai\envs\llm\python.exe" "%~dp0app\agent_server.py" --workdir "%WORKDIR%"

echo.
echo   App stopped. Press any key to close.
pause >nul
