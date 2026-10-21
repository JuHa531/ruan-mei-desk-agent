@echo off
rem ============================================================
rem  Recover Tailscale on Windows.
rem
rem  Symptom this fixes:
rem    `tailscale status` says "Tailscale is stopped." while two
rem    tailscaled.exe processes are fighting over the named pipe.
rem
rem  HOW TO RUN: right-click this file -> "Run as administrator"
rem  (Keep this file ASCII-only: cmd.exe reads .bat before the
rem   codepage is switched.)
rem ============================================================
title Fix Tailscale

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [!] Not running as administrator.
    echo       Close this window, right-click this file,
    echo       and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo.
echo   [1/4] stopping the Tailscale service...
net stop Tailscale

echo.
echo   [2/4] killing leftover tailscaled processes...
taskkill /F /IM tailscaled.exe
taskkill /F /IM tailscale-ipn.exe
timeout /t 3 /nobreak >nul

echo.
echo   [3/4] starting the Tailscale service...
net start Tailscale
timeout /t 8 /nobreak >nul

echo.
echo   [4/4] status:
"C:\Program Files\Tailscale\tailscale.exe" status

echo.
echo   If you see "100.x.x.x  ...  windows" above, it is healthy.
echo   Then go back to Codex and say so.
echo.
pause
