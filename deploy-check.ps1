param(
    [ValidateSet("sqlite", "postgresql")]
    [string]$Backend = "sqlite",

    [ValidateSet("in_process", "rq")]
    [string]$Queue = "in_process",

    [string]$DatabaseUrl = "",
    [string]$RedisUrl = "redis://localhost:6379/0",
    [switch]$ApiOnly
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

function Redact-Database-Url([string]$Value) {
    if (-not $Value) {
        return ""
    }
    try {
        $Uri = [System.Uri]$Value
        if ($Uri.UserInfo -and $Uri.UserInfo.Contains(":")) {
            $User = $Uri.UserInfo.Split(":", 2)[0]
            return $Value.Replace($Uri.UserInfo, "${User}:<redacted>")
        }
    } catch {
        return "<redacted>"
    }
    return $Value
}

if (-not (Test-Path $Python)) {
    Write-Host "Python virtual environment was not found. Run start.ps1 once first." -ForegroundColor Red
    exit 1
}

if (-not $DatabaseUrl) {
    if ($Backend -eq "sqlite") {
        $DatabaseUrl = "sqlite:///output/deploy-check-smoke.db"
    } else {
        throw "DatabaseUrl is required when Backend is postgresql."
    }
}

$env:DATABASE_URL = $DatabaseUrl
$env:QUEUE_BACKEND = $Queue

if ($Queue -eq "rq") {
    $env:REDIS_URL = $RedisUrl
    $env:START_BACKGROUND_WORKERS = "false"
    $env:START_NOTIFICATION_WORKER = "false"
} elseif ($ApiOnly) {
    $env:START_BACKGROUND_WORKERS = "false"
    $env:START_NOTIFICATION_WORKER = "false"
} else {
    $env:START_BACKGROUND_WORKERS = "true"
    $env:START_NOTIFICATION_WORKER = "true"
}

Write-Host "Running deploy check..." -ForegroundColor Cyan
Write-Host "  DATABASE_URL=$(Redact-Database-Url $env:DATABASE_URL)"
Write-Host "  QUEUE_BACKEND=$env:QUEUE_BACKEND"
if ($Queue -eq "rq") {
    Write-Host "  REDIS_URL=$env:REDIS_URL"
}
Write-Host "  START_BACKGROUND_WORKERS=$env:START_BACKGROUND_WORKERS"
Write-Host "  START_NOTIFICATION_WORKER=$env:START_NOTIFICATION_WORKER"

& $Python -m app.production_readiness_smoke --require-backend $Backend --require-queue $Queue
if ($LASTEXITCODE -ne 0) {
    throw "Deploy check failed with exit code $LASTEXITCODE"
}

Write-Host "Deploy check passed." -ForegroundColor Green
