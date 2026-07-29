param(
    [string]$DatabaseUrl = "",
    [string]$EnvPath = ".env",
    [string]$RedisUrl = "",
    [string]$ApiUrl = "http://127.0.0.1:8000/api/system/ping",
    [string]$TaskPrefix = "ProductMonitor",
    [string]$LogDir = "logs",
    [int]$LogTail = 20,
    [switch]$SkipApi,
    [switch]$SkipPostgres,
    [switch]$SkipRedis,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not [System.IO.Path]::IsPathRooted($EnvPath)) {
    $EnvPath = Join-Path $Root $EnvPath
}

if (-not [System.IO.Path]::IsPathRooted($LogDir)) {
    $LogDir = Join-Path $Root $LogDir
}

$Failures = 0
$Warnings = 0

function Write-CheckOk([string]$Name, [string]$Details = "") {
    if ($Details) {
        Write-Host "[ok] $Name - $Details" -ForegroundColor Green
    } else {
        Write-Host "[ok] $Name" -ForegroundColor Green
    }
}

function Write-CheckWarn([string]$Name, [string]$Details) {
    $script:Warnings += 1
    Write-Host "[warn] $Name - $Details" -ForegroundColor Yellow
}

function Write-CheckFail([string]$Name, [string]$Details) {
    $script:Failures += 1
    Write-Host "[fail] $Name - $Details" -ForegroundColor Red
}

function Invoke-CheckedCommand([string]$Name, [scriptblock]$Command) {
    try {
        $Output = & $Command 2>&1
        Write-CheckOk $Name (($Output | Select-Object -Last 1) -join "")
    } catch {
        Write-CheckFail $Name $_.Exception.Message
    }
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

function Redact-Secrets([string]$Value) {
    if (-not $Value) {
        return $Value
    }
    return ($Value -replace '(postgres(?:ql)?://[^:\s]+):([^@\s]+)@', '$1:<redacted>@')
}

function Test-ApiHealth {
    try {
        $Response = Invoke-RestMethod -Uri $ApiUrl -TimeoutSec 5
        $Status = if ($Response.status) { $Response.status } else { "response_received" }
        Write-CheckOk "api health" "$ApiUrl status=$Status"
    } catch {
        $Response = $_.Exception.Response
        if ($Response -and [int]$Response.StatusCode -eq 401) {
            Write-CheckOk "api health" "$ApiUrl reachable status=401 requires_auth"
            return
        }
        Write-CheckFail "api health" "$ApiUrl $($_.Exception.Message)"
    }
}

function Test-TaskStatus {
    $TaskNames = @(
        "$TaskPrefix-API",
        "$TaskPrefix-RQWorker",
        "$TaskPrefix-NotificationWorker",
        "$TaskPrefix-DatabaseBackup"
    )

    foreach ($TaskName in $TaskNames) {
        $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $Task) {
            Write-CheckWarn "scheduled task $TaskName" "missing"
            continue
        }

        $Info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
        $LastTaskResult = if ($Info) { $Info.LastTaskResult } else { "" }
        Write-CheckOk "scheduled task $TaskName" "state=$($Task.State) result=$LastTaskResult"
    }
}

function Show-LogTail([string]$Name, [string]$FileName) {
    $Path = Join-Path $LogDir $FileName
    if (-not (Test-Path $Path)) {
        Write-CheckWarn "log $Name" "missing $Path"
        return
    }

    Write-CheckOk "log $Name" $Path
    Get-Content $Path -Tail $LogTail | ForEach-Object { Redact-Secrets $_ }
}

Write-Host "Production health check" -ForegroundColor Cyan
Write-Host "  EnvPath=$EnvPath"
Write-Host "  ApiUrl=$ApiUrl"
Write-Host "  LogDir=$LogDir"

if (-not (Test-Path $Python)) {
    Write-CheckFail "python venv" "missing $Python"
} else {
    Write-CheckOk "python venv" $Python
}

if (-not $SkipPostgres) {
    if (-not $DatabaseUrl) {
        if ($env:DATABASE_URL) {
            $DatabaseUrl = $env:DATABASE_URL
        } elseif (Read-EnvValue $EnvPath "DATABASE_URL") {
            $DatabaseUrl = Read-EnvValue $EnvPath "DATABASE_URL"
        } else {
            Write-CheckWarn "postgresql" "DatabaseUrl not provided; skipping database preflight"
        }
    }
    if ($DatabaseUrl) {
        $env:DATABASE_URL = $DatabaseUrl
        Invoke-CheckedCommand "database health" { & $Python -m app.db_health }
    }
}

if (-not $SkipRedis) {
    if (-not $RedisUrl) {
        if ($env:REDIS_URL) {
            $RedisUrl = $env:REDIS_URL
        } elseif (Read-EnvValue $EnvPath "REDIS_URL") {
            $RedisUrl = Read-EnvValue $EnvPath "REDIS_URL"
        } else {
            $RedisUrl = "redis://127.0.0.1:6379/0"
        }
    }
    Write-Host "  RedisUrl=$RedisUrl"
    $env:QUEUE_BACKEND = "rq"
    $env:REDIS_URL = $RedisUrl
    Invoke-CheckedCommand "redis rq preflight" { & $Python -m app.rq_preflight --check-redis }
}

if (-not $SkipApi) {
    Test-ApiHealth
}

Test-TaskStatus
Show-LogTail "api" "api.log"
Show-LogTail "rq worker" "rq-worker.log"
Show-LogTail "notification worker" "notification-worker.log"

Write-Host "Health check summary: failures=$Failures warnings=$Warnings" -ForegroundColor Cyan

if ($Failures -gt 0 -or ($Strict -and $Warnings -gt 0)) {
    exit 1
}
