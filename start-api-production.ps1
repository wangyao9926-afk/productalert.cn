param(
    [string]$DatabaseUrl = "",
    [string]$EnvPath = ".env",
    [ValidateSet("in_process", "rq")]
    [string]$Queue = "rq",
    [string]$RedisUrl = "",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [string]$LogDir = "logs",
    [switch]$InsecureCookies,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not [System.IO.Path]::IsPathRooted($EnvPath)) {
    $EnvPath = Join-Path $Root $EnvPath
}

function Read-EnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path $Path)) {
        return ""
    }
    foreach ($Line in Get-Content $Path) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#")) {
            continue
        }
        $Parts = $Trimmed.Split("=", 2)
        if ($Parts.Count -eq 2 -and $Parts[0].Trim() -eq $Name) {
            return $Parts[1].Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

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
    if ($env:DATABASE_URL) {
        $DatabaseUrl = $env:DATABASE_URL
    } elseif (Read-EnvValue $EnvPath "DATABASE_URL") {
        $DatabaseUrl = Read-EnvValue $EnvPath "DATABASE_URL"
    } else {
        throw "DatabaseUrl is required for production API startup."
    }
}

if (-not $RedisUrl) {
    $RedisUrl = Read-EnvValue $EnvPath "REDIS_URL"
}
if (-not $RedisUrl -and $env:REDIS_URL) {
    $RedisUrl = $env:REDIS_URL
}
if (-not $RedisUrl) {
    $RedisUrl = "redis://127.0.0.1:6379/0"
}

$env:DATABASE_URL = $DatabaseUrl
$env:QUEUE_BACKEND = $Queue
$env:START_BACKGROUND_WORKERS = "false"
$env:START_NOTIFICATION_WORKER = "false"
$env:SESSION_COOKIE_SECURE = if ($InsecureCookies) { "false" } else { "true" }

if ($Queue -eq "rq") {
    $env:REDIS_URL = $RedisUrl
}

$ResolvedLogDir = ""
if ($LogDir) {
    if ([System.IO.Path]::IsPathRooted($LogDir)) {
        $ResolvedLogDir = $LogDir
    } else {
        $ResolvedLogDir = Join-Path $Root $LogDir
    }
}

$TranscriptStarted = $false
if (-not $DryRun -and $ResolvedLogDir) {
    New-Item -ItemType Directory -Force -Path $ResolvedLogDir | Out-Null
    Start-Transcript -Path (Join-Path $ResolvedLogDir "api.log") -Append | Out-Null
    $TranscriptStarted = $true
}

Write-Host "Starting production API..." -ForegroundColor Cyan
Write-Host "  ENV_PATH=$EnvPath"
Write-Host "  DATABASE_URL=$(Redact-Database-Url $env:DATABASE_URL)"
Write-Host "  QUEUE_BACKEND=$env:QUEUE_BACKEND"
if ($Queue -eq "rq") {
    Write-Host "  REDIS_URL=$env:REDIS_URL"
}
Write-Host "  START_BACKGROUND_WORKERS=$env:START_BACKGROUND_WORKERS"
Write-Host "  START_NOTIFICATION_WORKER=$env:START_NOTIFICATION_WORKER"
Write-Host "  SESSION_COOKIE_SECURE=$env:SESSION_COOKIE_SECURE"
Write-Host "  LOG_DIR=$ResolvedLogDir"
Write-Host "  URL=http://$HostName`:$Port"

if ($DryRun) {
    Write-Host "Dry run complete; API was not started." -ForegroundColor Yellow
    exit 0
}

try {
    & $Python -m uvicorn app.main:app --host $HostName --port $Port
} finally {
    if ($TranscriptStarted) {
        Stop-Transcript | Out-Null
    }
}
