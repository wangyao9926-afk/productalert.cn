param(
    [string]$EnvPath = ".env",
    [string]$DatabaseUrl = "",
    [string]$RedisUrl = "",
    [switch]$AllowInsecureCookies,
    [switch]$SkipApi,
    [switch]$SkipHealthCheck,
    [switch]$RunBackup,
    [int]$BackupKeepLast = 14,
    [switch]$RunRestoreDrill,
    [string]$RestoreBackupPath = "",
    [string]$AdminDatabaseUrl = "postgresql://postgres@127.0.0.1:5432/postgres",
    [string]$AdminPassword = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-Step([string]$Name, [scriptblock]$Command) {
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Env-Value([string]$Name) {
    if (-not (Test-Path $EnvPath)) {
        return ""
    }
    foreach ($Line in Get-Content $EnvPath) {
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

function Latest-BackupPath {
    $BackupDir = Join-Path $Root "backups"
    $Backup = Get-ChildItem -Path $BackupDir -Filter "product-monitor-*.dump" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $Backup) {
        throw "No product-monitor backup dump found in $BackupDir."
    }
    return $Backup.FullName
}

function Target-Database-Url([string]$SourceDatabaseUrl, [string]$TargetDatabaseName) {
    $Builder = [System.UriBuilder]::new($SourceDatabaseUrl)
    $Builder.Path = $TargetDatabaseName
    return $Builder.Uri.AbsoluteUri
}

if (-not [System.IO.Path]::IsPathRooted($EnvPath)) {
    $EnvPath = Join-Path $Root $EnvPath
}

if (-not $DatabaseUrl) {
    $DatabaseUrl = Env-Value "DATABASE_URL"
}
if (-not $RedisUrl) {
    $RedisUrl = Env-Value "REDIS_URL"
}

if (-not $DatabaseUrl) {
    throw "DatabaseUrl is required, either through -DatabaseUrl or DATABASE_URL in EnvPath."
}
if (-not $RedisUrl) {
    throw "RedisUrl is required, either through -RedisUrl or REDIS_URL in EnvPath."
}

Write-Host "Production preflight:" -ForegroundColor Cyan
Write-Host "  EnvPath=$EnvPath"
Write-Host "  DatabaseUrl=$(Redact-Database-Url $DatabaseUrl)"
Write-Host "  RedisUrl=$RedisUrl"
Write-Host "  RunBackup=$RunBackup"
Write-Host "  RunRestoreDrill=$RunRestoreDrill"

$ConfigArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $Root "check-production-config.ps1"),
    "-EnvPath", $EnvPath,
    "-DatabaseUrl", $DatabaseUrl,
    "-QueueBackend", "rq",
    "-RedisUrl", $RedisUrl,
    "-StartBackgroundWorkers", "false",
    "-StartNotificationWorker", "false"
)
if ($AllowInsecureCookies) {
    $ConfigArgs += @("-SessionCookieSecure", "false", "-AllowInsecureCookies")
} else {
    $ConfigArgs += @("-SessionCookieSecure", "true")
}

Invoke-Step "production config" {
    & powershell @ConfigArgs
}

Invoke-Step "release gate" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "deploy-check.ps1") `
        -Backend postgresql `
        -Queue rq `
        -DatabaseUrl $DatabaseUrl `
        -RedisUrl $RedisUrl
}

if ($RunBackup) {
    Invoke-Step "backup" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "run-scheduled-backup.ps1") `
            -DatabaseUrl $DatabaseUrl `
            -KeepLast $BackupKeepLast
    }
} else {
    Invoke-Step "backup dry-run" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "run-scheduled-backup.ps1") `
            -DryRun `
            -DatabaseUrl $DatabaseUrl `
            -KeepLast $BackupKeepLast
    }
}

if ($RunRestoreDrill) {
    if (-not $RestoreBackupPath) {
        $RestoreBackupPath = Latest-BackupPath
    } elseif (-not [System.IO.Path]::IsPathRooted($RestoreBackupPath)) {
        $RestoreBackupPath = Join-Path $Root $RestoreBackupPath
    }
    $TargetDatabaseName = "product_monitor_restore_drill_" + (Get-Date -Format "yyyyMMdd_HHmmss")
    $TargetDatabaseUrl = Target-Database-Url $DatabaseUrl $TargetDatabaseName
    $RestoreArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $Root "restore-drill-database.ps1"),
        "-BackupPath", $RestoreBackupPath,
        "-AdminDatabaseUrl", $AdminDatabaseUrl,
        "-TargetDatabaseName", $TargetDatabaseName,
        "-TargetDatabaseUrl", $TargetDatabaseUrl
    )
    if ($AdminPassword) {
        $RestoreArgs += @("-AdminPassword", $AdminPassword)
    }
    Invoke-Step "restore drill" {
        & powershell @RestoreArgs
    }
}

if (-not $SkipHealthCheck) {
    $HealthArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $Root "health-check-production.ps1"),
        "-EnvPath", $EnvPath
    )
    if ($SkipApi) {
        $HealthArgs += "-SkipApi"
    }
    Invoke-Step "health check" {
        & powershell @HealthArgs
    }
}

Write-Host ""
Write-Host "Production preflight completed." -ForegroundColor Green
