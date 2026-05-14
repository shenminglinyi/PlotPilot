# 清空 Plotpilot/data 下本地开发数据（SQLite、novels、bibles、storylines 等）。
# 若报错「文件正由另一进程使用」，请先停止 uvicorn / 后端再执行。

$ErrorActionPreference = "Stop"
$DataDir = Join-Path (Split-Path $PSScriptRoot -Parent) "data"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir | Out-Null
    Write-Host "Created empty $DataDir"
    exit 0
}
Get-ChildItem -LiteralPath $DataDir -Force | Remove-Item -Recurse -Force
Write-Host "Cleared: $DataDir"
