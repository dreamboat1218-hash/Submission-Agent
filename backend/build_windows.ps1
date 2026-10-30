# 在 Windows 上把后端打包成可执行目录（bid-agent-backend\bid-agent-backend.exe）
# 使用前请先在 frontend 目录执行 npm run build
param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"

$backend = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $backend
Set-Location $backend

if (-not $SkipInstall) {
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt pyinstaller
}

$dist = Join-Path $repo "frontend\dist"
if (-not (Test-Path (Join-Path $dist "index.html"))) {
    throw "前端未构建：请先执行 cd frontend && npm run build"
}

$knowledge = Join-Path $backend "knowledge_base"
$templates = Join-Path $backend "templates"
$scripts = Join-Path $backend "scripts"

pyinstaller --noconfirm --clean --onefile --name bid-agent-backend `
    --add-data "$dist;frontend/dist" `
    --add-data "$knowledge;knowledge_base" `
    --add-data "$templates;templates" `
    --add-data "$scripts;scripts" `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.lifespan.on `
    --collect-submodules app `
    --collect-submodules uvicorn `
    --collect-data docx `
    desktop_app.py

$exe = Join-Path $backend "dist\bid-agent-backend.exe"
if (-not (Test-Path $exe)) {
    throw "PyInstaller 构建失败，未生成 $exe"
}
Write-Host "后端构建完成：$exe"
