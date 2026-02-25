param(
    [switch]$ForceInstall,
    [switch]$SkipInstall,
    [switch]$SkipSeed,
    [switch]$ExposeHttps,
    [switch]$TunnelOnly,
    [ValidateSet("auto", "cloudflared", "ngrok")]
    [string]$TunnelProvider = "auto",
    [int]$TunnelPort = 8501
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Python312 {
    try {
        & py -3.12 -c "import sys; print(sys.version)" | Out-Null
    }
    catch {
        throw "Python 3.12 is required. Install it with: winget install --id Python.Python.3.12 -e"
    }
}

function Ensure-Venv([string]$DirPath) {
    $venvPython = Join-Path $DirPath ".venv\Scripts\python.exe"
    $created = $false

    if (-not (Test-Path $venvPython)) {
        Step "Creating virtual environment in $DirPath"
        Push-Location $DirPath
        & py -3.12 -m venv .venv
        Pop-Location
        $created = $true
    }

    return @{
        Python = $venvPython
        Created = $created
    }
}

function Wait-BackendReady([string]$HealthUrl, [int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
            if ($resp.status -eq "ok") {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

function Resolve-TunnelProvider([string]$Provider) {
    $hasCloudflared = $null -ne (Get-Command cloudflared -ErrorAction SilentlyContinue)
    $hasNgrok = $null -ne (Get-Command ngrok -ErrorAction SilentlyContinue)

    switch ($Provider) {
        "cloudflared" {
            if (-not $hasCloudflared) {
                throw "cloudflared is not installed. Install with: winget install Cloudflare.cloudflared"
            }
            return "cloudflared"
        }
        "ngrok" {
            if (-not $hasNgrok) {
                throw "ngrok is not installed. Install with: winget install Ngrok.Ngrok"
            }
            return "ngrok"
        }
        default {
            if ($hasCloudflared) { return "cloudflared" }
            if ($hasNgrok) { return "ngrok" }
            return $null
        }
    }
}

function Start-Tunnel([string]$Provider, [int]$Port) {
    $targetUrl = "http://127.0.0.1:$Port"
    if ($Provider -eq "cloudflared") {
        Write-Host "Using cloudflared to expose $targetUrl over HTTPS." -ForegroundColor Cyan
        & cloudflared tunnel --url $targetUrl
        return
    }
    if ($Provider -eq "ngrok") {
        Write-Host "Using ngrok to expose $targetUrl over HTTPS." -ForegroundColor Cyan
        & ngrok http $Port
        return
    }
    throw "Unsupported tunnel provider: $Provider"
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

if ($TunnelOnly) {
    Step "Starting HTTPS tunnel only"
    try {
        $resolvedTunnelProvider = Resolve-TunnelProvider -Provider $TunnelProvider
    }
    catch {
        throw $_
    }

    if (-not $resolvedTunnelProvider) {
        throw "No HTTPS tunnel tool found. Install one: winget install Cloudflare.cloudflared OR winget install Ngrok.Ngrok"
    }

    Start-Tunnel -Provider $resolvedTunnelProvider -Port $TunnelPort
    exit $LASTEXITCODE
}

Step "Checking prerequisites"
Ensure-Python312

if (-not (Test-Path (Join-Path $root ".env")) -and (Test-Path (Join-Path $root ".env.example"))) {
    Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
}

Step "Checking Docker daemon"
& docker info | Out-Null

Step "Starting Postgres container"
Push-Location $root
& docker compose up -d
Pop-Location

$backendEnv = Ensure-Venv -DirPath $backendDir
$frontendEnv = Ensure-Venv -DirPath $frontendDir
$backendPy = $backendEnv.Python
$frontendPy = $frontendEnv.Python

if (-not $SkipInstall) {
    Step "Installing backend dependencies"
    if ($backendEnv.Created -or $ForceInstall) {
        & $backendPy -m pip install --upgrade pip
    }
    & $backendPy -m pip install -r (Join-Path $backendDir "requirements.txt")

    Step "Installing frontend dependencies"
    if ($frontendEnv.Created -or $ForceInstall) {
        & $frontendPy -m pip install --upgrade pip
    }
    & $frontendPy -m pip install -r (Join-Path $frontendDir "requirements.txt")
}
else {
    Step "Skipping dependency install (-SkipInstall)"
}

Step "Initializing database"
Push-Location $backendDir
& $backendPy -m app.db.init_db
if (-not $SkipSeed) {
    & $backendPy -m app.db.seed
}
Pop-Location

Step "Launching backend and frontend"
$backendCmd = "Set-Location '$backendDir'; & '$backendPy' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
$frontendCmd = "Set-Location '$frontendDir'; `$env:BACKEND_URL='http://127.0.0.1:8000'; & '$frontendPy' -m streamlit run streamlit_app.py"

$backendProc = Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCmd -PassThru

Step "Waiting for backend health"
$ok = Wait-BackendReady -HealthUrl "http://127.0.0.1:8000/health" -TimeoutSeconds 60
if (-not $ok) {
    if ($backendProc.HasExited) {
        throw "Backend process exited before becoming healthy. Check backend terminal window for traceback."
    }
    throw "Backend did not become healthy within 60 seconds."
}

Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCmd | Out-Null

if ($ExposeHttps) {
    Step "Launching HTTPS tunnel terminal"
    Start-Process powershell.exe -ArgumentList `
        "-NoExit", `
        "-ExecutionPolicy", "Bypass", `
        "-File", $MyInvocation.MyCommand.Path, `
        "-TunnelOnly", `
        "-TunnelProvider", $TunnelProvider, `
        "-TunnelPort", $TunnelPort | Out-Null
}

Step "Done"
Write-Host "API docs: http://127.0.0.1:8000/docs"
Write-Host "UI:       http://localhost:8501"
if ($ExposeHttps) {
    Write-Host "HTTPS UI: check the tunnel terminal for the public https URL"
}
