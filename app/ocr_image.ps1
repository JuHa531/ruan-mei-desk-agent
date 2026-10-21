# 用 Windows 自带的 OCR 引擎识别图片里的文字（完全离线，不用装任何东西）。
# 由 agent_server.py 的 see_image 工具调用。
#
# 用法： powershell -ExecutionPolicy Bypass -File ocr_image.ps1 -Path "D:\a.png" -Lang zh-Hans-CN
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$Lang = "zh-Hans-CN"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime

# WinRT 的异步方法要用 AsTask 桥接到 .NET
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($op, $type) {
    $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

$full = (Resolve-Path -LiteralPath $Path).Path

$file    = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($full)) ([Windows.Storage.StorageFile])
$stream  = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap  = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = $null
try {
    $language = New-Object Windows.Globalization.Language $Lang
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
} catch { }
if (-not $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if (-not $engine) {
    Write-Output "[OCR 不可用] 这台机器没有安装任何 OCR 语言包"
    exit 2
}

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$lines = @()
foreach ($line in $result.Lines) { $lines += $line.Text }

$head = "[OCR] 语言=" + $engine.RecognizerLanguage.LanguageTag +
        " 尺寸=" + $decoder.PixelWidth + "x" + $decoder.PixelHeight
if ($lines.Count -eq 0) {
    Write-Output ($head + " 行数=0")
    Write-Output "[结果] 这张图上没有识别到文字（可能是纯照片、图表或手写体）。"
} else {
    Write-Output ($head + " 行数=" + $lines.Count)
    Write-Output "[结果]"
    foreach ($l in $lines) { Write-Output $l }
}
