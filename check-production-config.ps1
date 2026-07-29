param(
    [string]$EnvPath = ".env",
    [string]$DatabaseUrl = "",
    [string]$RedisUrl = "",
    [string]$QueueBackend = "",
    [string]$StartBackgroundWorkers = "",
    [string]$StartNotificationWorker = "",
    [string]$SessionCookieSecure = "",
    [switch]$AllowInsecureCookies
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not [System.IO.Path]::IsPathRooted($EnvPath)) {
    $EnvPath = Join-Path $Root $EnvPath
}

$Failures = 0
$Warnings = 0
$Config = @{}

function Add-Failure([string]$Message) {
    $script:Failures += 1
    Write-Host "[fail] $Message" -ForegroundColor Red
}

function Add-Warning([string]$Message) {
    $script:Warnings += 1
    Write-Host "[warn] $Message" -ForegroundColor Yellow
}

function Add-Ok([string]$Message) {
    Write-Host "[ok] $Message" -ForegroundColor Green
}

function Read-EnvFile([string]$Path) {
    if (-not (Test-Path $Path)) {
        Add-Warning "env file not found: $Path; using parameters and current environment only"
        return
    }
    foreach ($Line in Get-Content $Path) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#")) {
            continue
        }
        $Parts = $Trimmed.Split("=", 2)
        if ($Parts.Count -eq 2) {
            $script:Config[$Parts[0].Trim()] = $Parts[1].Trim().Trim('"').Trim("'")
        }
    }
}

function Config-Value([string]$Name, [string]$Explicit) {
    if ($Explicit) {
        return $Explicit
    }
    if ($Config.ContainsKey($Name)) {
        return $Config[$Name]
    }
    $EnvValue = [Environment]::GetEnvironmentVariable($Name)
    if ($EnvValue) {
        return $EnvValue
    }
    return ""
}

Read-EnvFile $EnvPath

$DatabaseUrl = Config-Value "DATABASE_URL" $DatabaseUrl
$RedisUrl = Config-Value "REDIS_URL" $RedisUrl
$QueueBackend = Config-Value "QUEUE_BACKEND" $QueueBackend
$StartBackgroundWorkers = Config-Value "START_BACKGROUND_WORKERS" $StartBackgroundWorkers
$StartNotificationWorker = Config-Value "START_NOTIFICATION_WORKER" $StartNotificationWorker
$SessionCookieSecure = Config-Value "SESSION_COOKIE_SECURE" $SessionCookieSecure

Write-Host "Production config check:" -ForegroundColor Cyan
Write-Host "  EnvPath=$EnvPath"

if (-not $DatabaseUrl) {
    Add-Failure "DATABASE_URL is required"
} elseif ($DatabaseUrl -notmatch "^(postgresql|postgres)://") {
    Add-Failure "DATABASE_URL must use PostgreSQL for production"
} else {
    Add-Ok "DATABASE_URL uses PostgreSQL"
    if ($DatabaseUrl -match "change-me|replace-with-strong-password|your-postgres-password") {
        Add-Failure "DATABASE_URL contains a placeholder or weak password marker"
    }
}

if (-not $QueueBackend) {
    Add-Failure "QUEUE_BACKEND is required"
} elseif ($QueueBackend -ne "rq") {
    Add-Failure "QUEUE_BACKEND must be rq for production"
} else {
    Add-Ok "QUEUE_BACKEND=rq"
}

if (-not $RedisUrl) {
    Add-Failure "REDIS_URL is required"
} elseif ($RedisUrl -notmatch "^redis://") {
    Add-Failure "REDIS_URL must start with redis://"
} else {
    Add-Ok "REDIS_URL configured"
}

if ($StartBackgroundWorkers -ne "false") {
    Add-Failure "START_BACKGROUND_WORKERS must be false for API-only production process"
} else {
    Add-Ok "START_BACKGROUND_WORKERS=false"
}

if ($StartNotificationWorker -ne "false") {
    Add-Failure "START_NOTIFICATION_WORKER must be false for API-only production process"
} else {
    Add-Ok "START_NOTIFICATION_WORKER=false"
}

if ($SessionCookieSecure -ne "true") {
    if ($AllowInsecureCookies) {
        Add-Warning "SESSION_COOKIE_SECURE is not true because AllowInsecureCookies was set"
    } else {
        Add-Failure "SESSION_COOKIE_SECURE must be true behind HTTPS"
    }
} else {
    Add-Ok "SESSION_COOKIE_SECURE=true"
}

Write-Host "Production config summary: failures=$Failures warnings=$Warnings" -ForegroundColor Cyan
if ($Failures -gt 0) {
    exit 1
}
