@echo off
rem ============================================================
rem  Yi Mei - microphone permission fix (run as administrator)
rem
rem  Symptom: the * voice-input button in the app always fails,
rem           the browser console says:
rem           NotAllowedError: Permission denied by system
rem
rem  Cause:   Windows privacy switch for the microphone is OFF.
rem           Measured on this PC 2026-10-11:
rem             HKLM ...\ConsentStore\microphone              = Deny
rem           (the same reason it fails inside Chrome and Edge,
rem            so it is not the app's fault)
rem
rem  This script only flips that switch back to Allow, the same
rem  thing the Settings app writes when you toggle it by hand.
rem  You can do it by hand instead:
rem    Settings - Privacy & security - Microphone -
rem      Microphone access ............ On
rem      Let apps access your microphone ... On
rem      Let desktop apps access your microphone ... On
rem
rem  Kept ASCII-only on purpose (cmd.exe reads .bat before the
rem  codepage is switched).
rem ============================================================

setlocal
set "KEY=HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [!] Need administrator rights.
    echo       Right-click this file - "Run as administrator" - then try again.
    echo.
    pause
    exit /b 1
)

echo.
echo   Before:
reg query "%KEY%" /v Value 2>nul
reg query "%KEY%\NonPackaged" /v Value 2>nul

reg add "%KEY%" /v Value /t REG_SZ /d Allow /f >nul
reg add "%KEY%\NonPackaged" /v Value /t REG_SZ /d Allow /f >nul

echo.
echo   After:
reg query "%KEY%" /v Value
reg query "%KEY%\NonPackaged" /v Value

echo.
echo   Done. Now close the Mei Mei window completely and open it again.
echo   (the app asks Windows for the microphone permission only once,
echo    so the window has to be reopened for the change to take effect)
echo.
pause
