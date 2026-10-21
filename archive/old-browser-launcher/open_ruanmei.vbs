' Launches the Ruan Mei local agent as a desktop app, with no console window.
' (Kept ASCII-only on purpose: WSH reads .vbs as ANSI.)
Option Explicit

Dim sh, fso, here, cmd
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here = fso.GetParentFolderName(WScript.ScriptFullName)
cmd  = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ _
       & here & "\rm_app.ps1"""
sh.Run cmd, 0, False
