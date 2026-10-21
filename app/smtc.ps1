# Read / control the music that is playing right now, through Windows SMTC
# (System Media Transport Controls).
#
# Why SMTC instead of faking media keys: media keys only reach whatever session
# happens to be "active"; SMTC is the system's own session table, so we can pick
# QQ Music by name, and we can also ask it what is playing.
#
# All output is ASCII KEY=VALUE lines; the Chinese wording is assembled on the
# python side (this file must stay ASCII-only - Windows PowerShell reads .ps1 as
# ANSI, and non-ASCII comments here have broken the parser before).
param(
    [string]$Action = "status",
    [string]$App = "QQMusic",
    [int]$Steps = 1,
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
# Collect every line in $out and emit at the very end.
# Why not just Say as we go: when we run without a console (the agent
# service spawns us), PowerShell writes to the pipe using the OEM codepage
# (GBK here), and the python side decoding as UTF-8 turns "Kua Zhang" into
# garbage. Writing with an explicit UTF-8 encoding is deterministic instead.
$out = New-Object System.Collections.ArrayList
function Say([string]$line) { [void]$out.Add($line) }
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
function Await($winRtTask, $resultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($resultType)
    $netTask = $asTask.Invoke($null, @($winRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

function MediaKey([byte]$vk, [int]$times = 1) {
    Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, System.UIntPtr dwExtraInfo);' -Name KB -Namespace MeiMei -ErrorAction SilentlyContinue | Out-Null
    for ($i = 0; $i -lt $times; $i++) {
        [MeiMei.KB]::keybd_event($vk, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 40
        [MeiMei.KB]::keybd_event($vk, 0, 2, [UIntPtr]::Zero)
    }
}

if ($Action -in @("vol_up", "vol_down", "mute")) {
    $vk = @{ vol_up = 0xAF; vol_down = 0xAE; mute = 0xAD }[$Action]
    MediaKey $vk $Steps
    Say "OK=volume-$Action"
    if ($OutFile) {
        [System.IO.File]::WriteAllLines($OutFile, $out, (New-Object System.Text.UTF8Encoding($false)))
    } else {
        $out | ForEach-Object { Write-Output $_ }
    }
    exit 0
}

[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null
$mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$sessions = @($mgr.GetSessions())
Say ("COUNT=" + $sessions.Count)

$s = $null
if ($App) {
    $s = $sessions | Where-Object { $_.SourceAppUserModelId -match $App } | Select-Object -First 1
}
if (-not $s -and $sessions.Count -ge 1) { $s = $sessions[0] }

if ($s) {
    $props = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
    Say ("APP=" + $s.SourceAppUserModelId)
    Say ("STATUS=" + $s.GetPlaybackInfo().PlaybackStatus)
    Say ("TITLE=" + $props.Title)
    Say ("ARTIST=" + $props.Artist)
    Say ("ALBUM=" + $props.AlbumTitle)
}

switch ($Action) {
    "play" { if ($s) { Say ("RESULT=" + (Await ($s.TryPlayAsync()) ([bool]))) } }
    "pause" { if ($s) { Say ("RESULT=" + (Await ($s.TryPauseAsync()) ([bool]))) } }
    "toggle" {
        if ($s) {
            $playing = $s.GetPlaybackInfo().PlaybackStatus -eq 4
            $r = if ($playing) { Await ($s.TryPauseAsync()) ([bool]) } else { Await ($s.TryPlayAsync()) ([bool]) }
            Say ("RESULT=" + $r)
        }
    }
    "next" { if ($s) { Say ("RESULT=" + (Await ($s.TrySkipNextAsync()) ([bool]))) } }
    "prev" { if ($s) { Say ("RESULT=" + (Await ($s.TrySkipPreviousAsync()) ([bool]))) } }
}

if ($s -and $Action -in @("play", "pause", "toggle", "next", "prev")) {
    Start-Sleep -Milliseconds 600
    $props2 = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
    Say ("AFTER_STATUS=" + $s.GetPlaybackInfo().PlaybackStatus)
    Say ("AFTER_TITLE=" + $props2.Title)
    Say ("AFTER_ARTIST=" + $props2.Artist)
}

if ($OutFile) {
    [System.IO.File]::WriteAllLines($OutFile, $out, (New-Object System.Text.UTF8Encoding($false)))
} else {
    $out | ForEach-Object { Write-Output $_ }
}
