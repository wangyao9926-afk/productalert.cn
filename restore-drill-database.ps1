param(
    [Parameter(Mandatory=$true)]
    [string]$BackupPath,
    [string]$AdminDatabaseUrl = "",
    [string]$AdminPassword = "",
    [string]$TargetDatabaseUrl = "",
    [string]$TargetDatabaseName = "",
    [string]$AppUser = "product_monitor",
    [string]$PsqlPath = "",
    [string]$PgRestorePath = "",
    [switch]$KeepDatabase,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not $AdminDatabaseUrl) {
    if ($env:POSTGRES_ADMIN_DATABASE_URL) {
        $AdminDatabaseUrl = $env:POSTGRES_ADMIN_DATABASE_URL
    } else {
        throw "AdminDatabaseUrl is required."
    }
}

if ($AdminDatabaseUrl -notmatch "^(postgresql|postgres)://") {
    throw "AdminDatabaseUrl must be a PostgreSQL URL."
}

if (-not $TargetDatabaseName) {
    $TargetDatabaseName = "product_monitor_restore_drill_" + (Get-Date -Format "yyyyMMdd_HHmmss")
}

if ($TargetDatabaseName -notmatch "^product_monitor_restore_drill_[A-Za-z0-9_]+$") {
    throw "TargetDatabaseName must start with product_monitor_restore_drill_ to avoid overwriting a real database."
}

function Resolve-ToolPath([string]$ConfiguredPath, [string]$ToolName) {
    if ($ConfiguredPath) {
        if (-not (Test-Path $ConfiguredPath)) {
            throw "$ToolName not found at $ConfiguredPath"
        }
        return $ConfiguredPath
    }

    $Command = Get-Command $ToolName -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $KnownPaths = @(
        "C:\Program Files\PostgreSQL\18\bin\$ToolName",
        "C:\Program Files\PostgreSQL\17\bin\$ToolName",
        "C:\Program Files\PostgreSQL\16\bin\$ToolName"
    )
    foreach ($Path in $KnownPaths) {
        if (Test-Path $Path) {
            return $Path
        }
    }

    throw "$ToolName was not found. Pass -${ToolName}Path or add PostgreSQL bin to PATH."
}

function With-DatabaseName([string]$DatabaseUrl, [string]$DatabaseName) {
    $Builder = [System.UriBuilder]::new($DatabaseUrl)
    $Builder.Path = $DatabaseName
    return $Builder.Uri.AbsoluteUri
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

if (-not [System.IO.Path]::IsPathRooted($BackupPath)) {
    $BackupPath = Join-Path $Root $BackupPath
}

$Psql = Resolve-ToolPath $PsqlPath "psql.exe"
$PgRestore = Resolve-ToolPath $PgRestorePath "pg_restore.exe"
$TargetAdminDatabaseUrl = With-DatabaseName $AdminDatabaseUrl $TargetDatabaseName
if (-not $TargetDatabaseUrl) {
    $TargetDatabaseUrl = "postgresql://$AppUser@127.0.0.1:5432/$TargetDatabaseName"
}

Write-Host "PostgreSQL restore drill plan:" -ForegroundColor Cyan
Write-Host "  backup=$BackupPath"
Write-Host "  psql=$Psql"
Write-Host "  pg_restore=$PgRestore"
Write-Host "  target_database=$TargetDatabaseName"
Write-Host "  target_admin_url=$(Redact-Database-Url $TargetAdminDatabaseUrl)"
Write-Host "  target_app_url=$(Redact-Database-Url $TargetDatabaseUrl)"
Write-Host "  app_user=$AppUser"
Write-Host "  keep_database=$KeepDatabase"

if ($DryRun) {
    Write-Host "Dry run complete; no database was created or restored." -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path $BackupPath)) {
    throw "Backup file not found: $BackupPath"
}

if (-not (Test-Path $Python)) {
    throw "Python virtual environment was not found: $Python"
}

$Created = $false
$PreviousPgPassword = $env:PGPASSWORD
try {
    if ($AdminPassword) {
        $env:PGPASSWORD = $AdminPassword
    }
    & $Psql $AdminDatabaseUrl -v ON_ERROR_STOP=1 -c "CREATE DATABASE $TargetDatabaseName OWNER $AppUser;"
    if ($LASTEXITCODE -ne 0) {
        throw "CREATE DATABASE failed with exit code $LASTEXITCODE"
    }
    $Created = $true

    & $PgRestore --dbname $TargetAdminDatabaseUrl --no-owner --no-acl $BackupPath
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed with exit code $LASTEXITCODE"
    }

    $env:DATABASE_URL = $TargetDatabaseUrl
    & $Python -m app.db_health
    if ($LASTEXITCODE -ne 0) {
        throw "restored database health check failed with exit code $LASTEXITCODE"
    }

    Write-Host "Restore drill passed for $TargetDatabaseName" -ForegroundColor Green
} finally {
    if ($Created -and -not $KeepDatabase) {
        & $Psql $AdminDatabaseUrl -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $TargetDatabaseName WITH (FORCE);"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Dropped restore drill database $TargetDatabaseName" -ForegroundColor Yellow
        } else {
            Write-Host "Failed to drop restore drill database $TargetDatabaseName" -ForegroundColor Red
        }
    }
    $env:PGPASSWORD = $PreviousPgPassword
}
