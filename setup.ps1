# Antigravity Chrome Bridge - Windows Setup Script
$ErrorActionPreference = "Stop"

Write-Host "📦 Initializing Antigravity Chrome Bridge on Windows..." -ForegroundColor Cyan

# 1. Check Python
$pythonCmd = $null
if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $pythonCmd = "py -3.11"
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
}

if (-not $pythonCmd) {
    Write-Host "⚠️ Python not found. Please install Python 3.10+ (winget install Python.Python.3.11)." -ForegroundColor Yellow
}

# 2. Check Node
if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Node.js is required for Native Messaging Host. Please install Node.js (winget install OpenJS.NodeJS.LTS)." -ForegroundColor Red
    exit 1
}

# 3. Run cross-platform setup-host.mjs
Write-Host "🚀 Running host and environment setup..." -ForegroundColor Green
node setup-host.mjs

Write-Host "`n🎉 Setup completed successfully!" -ForegroundColor Green
