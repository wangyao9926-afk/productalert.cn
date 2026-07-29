$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
  Write-Host "未找到虚拟环境，正在创建并安装依赖..."
  python -m venv (Join-Path $Root ".venv")
  & $Python -m pip install -r (Join-Path $Root "requirements.txt")
}

Write-Host "新品上新通知工具已启动：http://127.0.0.1:8000"
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
