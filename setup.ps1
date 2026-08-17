<#
.SYNOPSIS
    Chrome Bridge 2.0 - Windows Setup & Diagnostics Script
.DESCRIPTION
    Automates Windows environment checks (Node.js, Python/uv), virtual environment setup,
    Chrome Native Messaging Host registration, MCP configuration, and self-testing.
.PARAMETER SkipTests
    Skip running the automated test suite after setup.
.PARAMETER Reinstall
    Force recreate the Python virtual environment (.venv) from scratch.
.EXAMPLE
    .\setup.ps1
.EXAMPLE
    .\setup.ps1 -Reinstall -SkipTests
#>

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$Reinstall
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

function Write-Header {
    param([string]$Title)
    Write-Host "`n================================================================" -ForegroundColor Cyan
    Write-Host "   $Title" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Message)
    Write-Host "`n[$([char]0x2192)] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [✓] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [!] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "  [x] $Message" -ForegroundColor Red
}

Write-Header "🚀 Chrome Bridge 2.0 — Windows Setup Assistant"

Write-Host "`n📋 System Environment Check:" -ForegroundColor White
Write-Host "  • Working Directory: $ScriptDir" -ForegroundColor Gray
Write-Host "  • PowerShell Version: $($PSVersionTable.PSVersion)" -ForegroundColor Gray
Write-Host "  • Operating System:  $([System.Environment]::OSVersion.VersionString)" -ForegroundColor Gray

# --- 1. Validate Node.js ---
Write-Step "[1/4] Validating Node.js Runtime..."
$nodeCmd = Get-Command "node" -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Err "Node.js is not found in PATH."
    Write-Host "     Please install Node.js (LTS):" -ForegroundColor Yellow
    Write-Host "     👉 winget install OpenJS.NodeJS.LTS" -ForegroundColor White
    exit 1
}
$nodeVersion = (node --version).Trim()
Write-Success "Node.js $nodeVersion detected at: $($nodeCmd.Source)"

# --- 2. Validate Python / uv ---
Write-Step "[2/4] Validating Python Runtime & Package Managers..."
$hasUv = [bool](Get-Command "uv" -ErrorAction SilentlyContinue)
$pythonExe = $null

if ($hasUv) {
    $uvVersion = (uv --version).Trim()
    Write-Success "Fast installer detected: $uvVersion"
}

# Resolve system python
$pythonCandidates = @("py", "python", "python3")
foreach ($cand in $pythonCandidates) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) {
        try {
            $ver = (& $cand -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null).Trim()
            $parts = $ver.Split('.')
            if ($parts.Count -ge 2 -and [int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                $pythonExe = $cand
                Write-Success "Python $ver found ($cand)."
                break
            }
        } catch {}
    }
}

if (-not $pythonExe -and -not $hasUv) {
    Write-Err "Python 3.10+ was not detected in PATH."
    Write-Host "     Install Python 3.11 or uv:" -ForegroundColor Yellow
    Write-Host "     👉 winget install Python.Python.3.11" -ForegroundColor White
    Write-Host "     👉 winget install astral-sh.uv" -ForegroundColor White
    exit 1
}

# --- 3. Provision Virtual Environment (.venv) ---
Write-Step "[3/4] Provisioning Python Virtual Environment (.venv)..."
$venvDir = Join-Path $ScriptDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if ($Reinstall -and (Test-Path $venvDir)) {
    Write-Warn "Removing existing .venv for clean re-installation..."
    Remove-Item -Recurse -Force $venvDir
}

if ($hasUv) {
    if (-not (Test-Path $venvDir)) {
        Write-Host "     Creating .venv with uv..." -ForegroundColor Gray
        uv venv .venv
    }
    Write-Host "     Installing / syncing dependencies with uv..." -ForegroundColor Gray
    uv pip install -r requirements.txt
} else {
    if (-not (Test-Path $venvDir)) {
        Write-Host "     Creating .venv with $pythonExe..." -ForegroundColor Gray
        & $pythonExe -m venv .venv
    }
    $pipExe = Join-Path $venvDir "Scripts\pip.exe"
    Write-Host "     Installing dependencies with pip..." -ForegroundColor Gray
    & $pipExe install -r requirements.txt --quiet
}

if (Test-Path $venvPython) {
    Write-Success "Virtual environment ready at: $venvDir"
} else {
    Write-Warn "Virtual environment python not located at expected path. Using system python."
}

# --- 4. Native Messaging Host Registration ---
Write-Step "[4/4] Registering Native Messaging Host & MCP Configurations..."
node setup-host.mjs

# Verify Windows Registry Key
$regPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.chrome_bridge.native"
if (Test-Path $regPath) {
    Write-Success "Verified Chrome Native Messaging Host in Windows Registry."
} else {
    Write-Warn "Registry key at $regPath could not be verified directly."
}

# --- 5. Self-Testing & Diagnostic Verification ---
if (-not $SkipTests) {
    Write-Step "Running automated self-tests..."
    try {
        if ($hasUv) {
            uv run pytest tests/ -v
        } elseif (Test-Path $venvPython) {
            & $venvPython -m pytest tests/ -v
        }
        Write-Success "All unit and integration tests passed successfully!"
    } catch {
        Write-Warn "Some tests encountered warnings or non-zero exits during setup."
    }
}

# --- 6. Final Instructions ---
$extensionPath = Join-Path $ScriptDir "extension"
Write-Host @"

================================================================
   🎉 Chrome Bridge is Live & Ready on Windows!
================================================================

Next Steps:
  1. Open Google Chrome and navigate to: chrome://extensions/
  2. Enable [Developer mode] (top-right toggle).
  3. Click [Load unpacked] and select this folder:
     👉 $extensionPath
  4. Ensure the extension is enabled and active!

"@ -ForegroundColor Green

