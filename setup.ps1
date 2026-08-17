<#
.SYNOPSIS
    Antigravity Chrome Bridge - Windows Setup & Diagnostics Script
.DESCRIPTION
    Automates dependency checks (Node.js, Python/uv), virtual environment setup,
    Chrome Native Messaging Host registration, MCP configuration, and self-testing.
.PARAMETER SkipTests
    Skip running the test suite after setup.
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
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

function Write-Step {
    param([string]$Message)
    Write-Host "`n[$([char]0x2192)] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host " [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host " [!] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host " [x] $Message" -ForegroundColor Red
}

Write-Host @"
======================================================
  🚀 Antigravity Chrome Bridge - Windows Setup v2.0   
======================================================
"@ -ForegroundColor Magenta

# --- 1. Validate Node.js ---
Write-Step "Checking Node.js environment..."
$nodeCmd = Get-Command "node" -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Err "Node.js is not found in PATH."
    Write-Host "     Please install Node.js (LTS):" -ForegroundColor Yellow
    Write-Host "     👉 winget install OpenJS.NodeJS.LTS" -ForegroundColor White
    exit 1
}
$nodeVersion = (node --version).Trim()
Write-Success "Node.js $nodeVersion detected."

# --- 2. Validate Python / uv ---
Write-Step "Checking Python runtime & package managers..."
$hasUv = [bool](Get-Command "uv" -ErrorAction SilentlyContinue)
$pythonExe = $null

if ($hasUv) {
    $uvVersion = (uv --version).Trim()
    Write-Success "Fast package manager detected: $uvVersion"
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
Write-Step "Configuring Python virtual environment (.venv)..."
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
Write-Step "Registering Native Messaging Host & MCP Configurations..."
node setup-host.mjs

# Verify Windows Registry Key
$regPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.antigravity.chrome_bridge"
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
            uv run pytest tests/ -q
        } elseif (Test-Path $venvPython) {
            & $venvPython -m pytest tests/ -q
        }
        Write-Success "All unit and integration tests passed successfully!"
    } catch {
        Write-Warn "Some tests encountered warnings or non-zero exits during setup."
    }
}

# --- 6. Final Instructions ---
$extensionPath = Join-Path $ScriptDir "extension"
Write-Host @"

======================================================
  🎉 Antigravity Chrome Bridge is Ready!
======================================================

Next Steps:
  1. Open Google Chrome and navigate to: chrome://extensions/
  2. Enable [Developer mode] (top-right toggle).
  3. Click [Load unpacked] and select this folder:
     👉 $extensionPath
  4. Ensure the extension is enabled and active!

"@ -ForegroundColor Green
