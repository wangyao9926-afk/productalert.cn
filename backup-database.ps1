param(
    [string]$DatabaseUrl = "",
    [string]$OutputDir = "backups",
    [string]$PgDumpPath = "",
    [string]$PgRestorePath = "",
    [string]$FileName = "",
    [switch]$Verify,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $DatabaseUrl) {
    if ($env:DATABASE_URL) {
        $DatabaseUrl = $env:DATABASE_URL
    } else {
        throw "DatabaseUrl is required."
    }
}

if ($DatabaseUrl -notmatch "^(postgresql|postgres)://") {
    throw "backup-database.ps1 currently supports PostgreSQL DATABASE_URL values only."
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

if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir = Join-Path $Root $OutputDir
}

if (-not $FileName) {
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $FileName = "product-monitor-$Stamp.dump"
}

$BackupPath = Join-Path $OutputDir $FileName
$PgDump = Resolve-ToolPath $PgDumpPath "pg_dump.exe"
$PgRestore = ""
if ($Verify) {
    $PgRestore = Resolve-ToolPath $PgRestorePath "pg_restore.exe"
}

Write-Host "PostgreSQL backup plan:" -ForegroundColor Cyan
Write-Host "  pg_dump=$PgDump"
if ($Verify) {
    Write-Host "  pg_restore=$PgRestore"
}
Write-Host "  output=$BackupPath"
Write-Host "  verify=$Verify"

if ($DryRun) {
    Write-Host "Dry run complete; no backup was created." -ForegroundColor Yellow
    exit 0
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

& $PgDump --format=custom --no-owner --no-acl --file $BackupPath $DatabaseUrl
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $BackupPath)) {
    throw "Backup file was not created: $BackupPath"
}

$BackupFile = Get-Item $BackupPath
if ($BackupFile.Length -le 0) {
    throw "Backup file is empty: $BackupPath"
}

Write-Host "Backup created: $BackupPath size_bytes=$($BackupFile.Length)" -ForegroundColor Green

if ($Verify) {
    & $PgRestore --list $BackupPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore --list failed with exit code $LASTEXITCODE"
    }
    Write-Host "Backup verified with pg_restore --list." -ForegroundColor Green
}
