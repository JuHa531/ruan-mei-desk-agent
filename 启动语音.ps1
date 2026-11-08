# 一键启动「阮·梅」的语音链路
#
# 用法（在 PowerShell 里）：
#     powershell -ExecutionPolicy Bypass -File .\启动语音.ps1
#
# 会启动两个进程：
#     GPT-SoVITS   端口 9880   （独立环境 D:\ai\envs\tts）
#     语音适配器    端口 9881   （任意环境，零依赖）
#
# Ollama 是 Windows 服务，开机自动运行，不用手动起。

$ErrorActionPreference = "Stop"
$VoiceStartupMutex = New-Object System.Threading.Mutex($false, "Local\MeiMeiVoiceStartup")
try { $VoiceStartupOwned = $VoiceStartupMutex.WaitOne(0) }
catch [System.Threading.AbandonedMutexException] { $VoiceStartupOwned = $true }
if (-not $VoiceStartupOwned) {
    Write-Host "Voice startup is already in progress."
    $VoiceStartupMutex.Dispose()
    exit 0
}

$GsRoot   = "G:\ai\GPT-SoVITS\GPT-SoVITS-main"
$GsPython = "D:\ai\envs\tts\python.exe"
$Adapter  = "C:\Users\qqqqq\Documents\Codex\2026-10-06\wo\outputs\local-ai-toolkit\voice\tts_server.py"
$Config   = "C:\Users\qqqqq\Documents\Codex\2026-10-06\wo\outputs\local-ai-toolkit\voice\voices.json"
$AdPython = "D:\ai\envs\meimei-app\Scripts\python.exe"
$Asr      = "C:\Users\qqqqq\Documents\Codex\2026-10-06\wo\outputs\local-ai-toolkit\voice\asr_server.py"
$LogDir   = Join-Path (Split-Path (Split-Path $Adapter)) "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Test-Port($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

Write-Host "检查服务状态……" -ForegroundColor Cyan

if (Test-Port 9880) {
    Write-Host "  [跳过] GPT-SoVITS 已在运行（9880）" -ForegroundColor Yellow
} else {
    Write-Host "  [启动] GPT-SoVITS（首次调用要预热约 5 分钟）"
    $GsApi = Join-Path (Split-Path $Adapter) "gptsovits_local_api.py"
    Start-Process -FilePath $GsPython -ArgumentList $GsApi, "-a", "127.0.0.1", "-p", "9880" `
        -WorkingDirectory $GsRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "gptsovits.stdout.log") `
        -RedirectStandardError (Join-Path $LogDir "gptsovits.stderr.log")
}

Start-Sleep -Seconds 3

if (Test-Port 9881) {
    Write-Host "  [跳过] 语音适配器 已在运行（9881）" -ForegroundColor Yellow
} else {
    Write-Host "  [启动] 语音适配器（9881）"
    Start-Process -FilePath $AdPython -ArgumentList $Adapter, "--config", $Config `
        -WorkingDirectory (Split-Path $Adapter) -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "tts.stdout.log") `
        -RedirectStandardError (Join-Path $LogDir "tts.stderr.log")
}

# 语音识别（听你说话）：必须用 tts 环境，funasr 和模型都在里面
if (Test-Port 9882) {
    Write-Host "  [跳过] 语音识别 已在运行（9882）" -ForegroundColor Yellow
} else {
    Write-Host "  [启动] 语音识别（9882，首次加载模型约 10 秒）"
    # Recognition is independent of synthesis. Load it only when first used.
    # Set RM_ASR_PRELOAD=1 to retain immediate first microphone recognition.
    $AsrArgs = @($Asr)
    if ($env:RM_ASR_PRELOAD -eq '1') { $AsrArgs += '--preload' }
    Start-Process -FilePath $GsPython -ArgumentList $AsrArgs `
        -WorkingDirectory (Split-Path $Asr) -WindowStyle Hidden -RedirectStandardOutput "C:\Users\qqqqq\AppData\Local\Temp\rm_asr.log" -RedirectStandardError "C:\Users\qqqqq\AppData\Local\Temp\rm_asr.err"
}

Write-Host ""
Write-Host "等待就绪……" -ForegroundColor Cyan
$ok9880 = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 4
    if (Test-Port 9880) { $ok9880 = $true; break }
}

# 权重选择
# ------------------------------------------------------------------
# $UseFinetune = $false  -> 用原始预训练权重做零样本克隆
# $UseFinetune = $true   -> 加载精调权重（当前选择，2026-10-20 重训）
#
# 2026-10-20 用「阮梅全语音」+「苏州博物馆导览语音」重训：
# 341 条、25.9 分钟；A/B 试听样本在 G:\ai\voice\ab\。
# 新权重合成同一句：转写完整、静音段约 -93 dB（旧素材是 -29~-35 dB），
# 不再有之前那层明显的背景音乐底噪。要回退零样本，把这里改回 $false。
$UseFinetune = $true

if ($ok9880 -and -not $UseFinetune) {
    Write-Host "  [OK] 使用原始预训练权重（零样本克隆，音色干净）" -ForegroundColor Green
}

if ($ok9880 -and $UseFinetune) {
    $gpt = "GPT_weights_v2/ruanmei_refine_20261027-e10.ckpt"
    $sov = "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth"
    foreach ($pair in @(@('GPT', $gpt), @('SoVITS', $sov))) {
        # Keep already-loaded weights resident instead of loading them twice.
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:9880/healthz' -TimeoutSec 10
            $weightKey = $pair[0].ToLower()
            $loadedPath = $health.weights.$weightKey
            $wantedPath = [System.IO.Path]::GetFullPath((Join-Path $GsRoot $pair[1]))
            if ($loadedPath -and ([System.IO.Path]::GetFullPath($loadedPath) -eq $wantedPath)) {
                Write-Host ("  [OK] $($pair[0]) weights already loaded") -ForegroundColor Green
                continue
            }
        } catch { }
        $enc = [uri]::EscapeDataString($pair[1])
        $done = $false
        # 服务刚起来时接口还不能用，多试几次（最多约 1 分钟）
        for ($try = 1; $try -le 8 -and -not $done; $try++) {
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:9880/set_$($pair[0].ToLower())_weights?weights_path=$enc" `
                    -TimeoutSec 120 -UseBasicParsing -ErrorAction Stop
                if ($resp.Content -match "success") {
                    $done = $true
                    Write-Host ("  [OK] 已加载精调 $($pair[0]) 权重") -ForegroundColor Green
                }
            } catch { }
            if (-not $done) { Start-Sleep -Seconds 8 }
        }
        if (-not $done) {
            Write-Host ("  [警告] 加载精调 $($pair[0]) 权重失败，将使用默认权重（声音会略钝）") -ForegroundColor Yellow
        }
    }
}

$ok9881 = $false
for ($i = 0; $i -lt 10; $i++) {
    if (Test-Port 9881) { $ok9881 = $true; break }
    Start-Sleep -Seconds 2
}

$ok9882 = $false
for ($i = 0; $i -lt 20; $i++) {
    if (Test-Port 9882) { $ok9882 = $true; break }
    Start-Sleep -Seconds 3
}

Write-Host ""
if ($ok9880) { Write-Host "  [OK] GPT-SoVITS   http://127.0.0.1:9880" -ForegroundColor Green }
else { Write-Host "  [!!] GPT-SoVITS 未能启动，检查日志" -ForegroundColor Red }
if ($ok9881) { Write-Host "  [OK] 语音适配器   http://127.0.0.1:9881" -ForegroundColor Green }
else { Write-Host "  [!!] 适配器未能启动" -ForegroundColor Red }
if ($ok9882) { Write-Host "  [OK] 语音识别     http://127.0.0.1:9882" -ForegroundColor Green }
else { Write-Host "  [!!] 语音识别未能启动（界面上麦克风会不可用）" -ForegroundColor Red }

Write-Host ""
Write-Host "Open WebUI 里这样填：" -ForegroundColor Cyan
Write-Host "  设置 -> 音频 -> TTS 引擎选 OpenAI"
Write-Host "  API Base URL   http://127.0.0.1:9881/v1"
Write-Host "  API Key        随便填"
Write-Host "  TTS Voice      ruanmei"
Write-Host ""
Write-Host "第一次合成会等 5 分钟左右（模型预热），之后每次 1~2 秒。" -ForegroundColor Yellow
$VoiceStartupMutex.ReleaseMutex()
$VoiceStartupMutex.Dispose()
