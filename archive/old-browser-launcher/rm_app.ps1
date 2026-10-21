# 一键把「阮·梅」当桌面应用打开（没有控制台窗口，不需要你记命令）
#
# 它按顺序做四件事：
#   1. 语音链路（GPT-SoVITS 9880 + 语音适配器 9881）没开就后台开
#   2. 应用本体（agent_server 7788）没开就后台开
#   3. 等端口就绪
#   4. 用浏览器的「应用模式」打开 —— 独立窗口、没有地址栏，跟正常桌面软件一样

$ErrorActionPreference = "Continue"

$Root    = "C:\Users\qqqqq\Documents\Codex\2026-10-06\wo\outputs\local-ai-toolkit"
$Python  = "D:\ai\envs\llm\python.exe"
$WorkDir = Join-Path $env:USERPROFILE "Documents\rm-workspace"
$Url     = "http://127.0.0.1:7788/"

function Test-Port($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Path $WorkDir)) {
    New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
}

# 1) 语音链路（它自己的脚本会判断要不要起、会加载精调权重）
if (-not (Test-Port 9880) -or -not (Test-Port 9881)) {
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", (Join-Path $Root "启动语音.ps1") `
        -WindowStyle Hidden
}

# 2) 应用本体
if (-not (Test-Port 7788)) {
    Start-Process -FilePath $Python `
        -ArgumentList (Join-Path $Root "app\agent_server.py"), "--no-browser", "--workdir", $WorkDir `
        -WorkingDirectory $Root -WindowStyle Hidden
}

# 3) 等它就绪
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Port 7788) { $ok = $true; break }
}

if (-not $ok) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "应用没起来。请双击 toolkit 目录里的「启动阮梅.bat」看报错信息。",
        "梅梅", "OK", "Warning") | Out-Null
    exit 1
}

# 4) 应用模式打开（独立窗口）
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$edge   = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# 独立 profile：保证一定是「应用窗口」（没有地址栏/标签页），
# 也不会和你平时上网的浏览器窗口混在一起。
$AppProfile = Join-Path $Root "app\app-profile"
if (-not (Test-Path $AppProfile)) { New-Item -ItemType Directory -Force -Path $AppProfile | Out-Null }

$appArgs = @("--app=$Url", "--start-maximized",
             "--user-data-dir=$AppProfile",
             "--no-first-run", "--no-default-browser-check",
             "--lang=zh-CN", "--disable-features=Translate",
             # 让 Chrome 把窗口标题栏也画成深色（浅色主题下它默认画一条浅色栏，
             # 实测不会影响页面本身的配色，只影响浏览器自己的界面）
             "--force-dark-mode")
if (Test-Path $chrome) {
    Start-Process -FilePath $chrome -ArgumentList $appArgs
} elseif (Test-Path $edge) {
    Start-Process -FilePath $edge -ArgumentList $appArgs
} else {
    Start-Process $Url
}

# 5) 把窗口顶部那条原生标题栏刷成深色。
#    你的 Windows 现在是浅色主题，标题栏默认被画成白色，压在深色界面上很突兀。
#    这里直接告诉 DWM：这条窗口用深色标题栏 + 深色底 + 浅色字。
#    想恢复系统默认：把文件最后一行 Set-DarkTitleBar 注释掉就行。
Add-Type -Namespace RMToolkit -Name Dwm -MemberDefinition @'
[DllImport("dwmapi.dll")]
public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
'@ -ErrorAction SilentlyContinue

function Set-DarkTitleBar {
    for ($i = 0; $i -lt 50; $i++) {
        $p = Get-Process -Name chrome, msedge -ErrorAction SilentlyContinue |
             Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*梅梅*" } |
             Select-Object -First 1
        if ($p) {
            $h  = $p.MainWindowHandle
            $on = 1
            [void][RMToolkit.Dwm]::DwmSetWindowAttribute($h, 20, [ref]$on, 4)   # 深色标题栏
            [void][RMToolkit.Dwm]::DwmSetWindowAttribute($h, 19, [ref]$on, 4)   # 旧版 Windows 的编号
            $cap = 0x00120D0B    # 标题栏底色 = #0b0d12（COLORREF 是 BGR 顺序）
            [void][RMToolkit.Dwm]::DwmSetWindowAttribute($h, 35, [ref]$cap, 4)
            $txt = 0x00F3ECE8    # 标题栏文字 = #e8ecf3
            [void][RMToolkit.Dwm]::DwmSetWindowAttribute($h, 36, [ref]$txt, 4)
            return
        }
        Start-Sleep -Milliseconds 400
    }
}
Set-DarkTitleBar
