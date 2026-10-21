<#
  阶段 0：把所有「大文件」目录挪到 G 盘，并建好目录骨架。

  用法（普通 PowerShell 窗口，不需要管理员）：
      powershell -ExecutionPolicy Bypass -File .\setup_env.ps1

  只写「当前用户」级环境变量，想改路径随时重跑一次即可，不会影响系统其他部分。
#>

$ErrorActionPreference = "Stop"

$Root = "G:\ai"

$dirs = @(
    $Root,
    "$Root\ollama-models",
    "$Root\conda-pkgs",
    "$Root\pip-cache",
    "$Root\hf-cache",
    "$Root\torch-cache",
    "$Root\envs",
    "$Root\data",
    "$Root\out",
    "$Root\logs"
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# 这些变量名是各工具官方支持的，不要改名字
$vars = [ordered]@{
    "OLLAMA_MODELS"   = "$Root\ollama-models"   # ollama 下载的模型
    "CONDA_PKGS_DIRS" = "$Root\conda-pkgs"      # conda 包缓存（默认会吃掉 C 盘好几个 G）
    "PIP_CACHE_DIR"   = "$Root\pip-cache"       # pip 下载缓存
    "HF_HOME"         = "$Root\hf-cache"        # HuggingFace 模型缓存（最占地方的一个）
    "TORCH_HOME"      = "$Root\torch-cache"     # torch 预训练权重缓存
}

Write-Host "已设置用户级环境变量：" -ForegroundColor Cyan
foreach ($k in $vars.Keys) {
    [Environment]::SetEnvironmentVariable($k, $vars[$k], "User")
    Set-Item -Path "Env:$k" -Value $vars[$k]     # 让当前窗口立即生效
    Write-Host ("  {0,-16} = {1}" -f $k, $vars[$k])
}

Write-Host ""
Write-Host "目录骨架已建好：$Root" -ForegroundColor Green
$g = Get-PSDrive -Name G
Write-Host ("G 盘剩余空间：{0} GB" -f [math]::Round($g.Free / 1GB, 1))

Write-Host ""
Write-Host "下一步：关掉这个窗口、重新开一个（让变量对新窗口生效），然后去装 Ollama。"
