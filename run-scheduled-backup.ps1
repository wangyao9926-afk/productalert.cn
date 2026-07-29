param(
    [string]$DatabaseUrl = "",
    [string]$EnvPath = ".env",
    [string]$OutputDir = "backups",
    [int]$KeepLast = 14,
    [string]$PgDumpPath = "",
    [string]$PgRestorePath = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

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

if ($KeepLast -lt 1) {
    throw "KeepLast must be at least 1."
}

if (-not $DatabaseUrl) {
    if ($env:DATABASE_URL) {
        $DatabaseUrl = $env:DATABASE_URL
    } elseif (Read-EnvValue $EnvPath "DATABASE_URL") {
        $DatabaseUrl = Read-EnvValue $EnvPath "DATABASE_URL"
    } else {
        throw "DatabaseUrl is required."
    }
}

if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir = Join-Path $Root $OutputDir
}

function Backup-Arguments([string]$FileName) {
    $Args = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $Root "backup-database.ps1"),
        "-DatabaseUrl", $DatabaseUrl,
        "-OutputDir", $OutputDir,
        "-FileName", $FileName,
        "-Verify"
    )
    if ($PgDumpPath) {
        $Args += @("-PgDumpPath", $PgDumpPath)
    }
    if ($PgRestorePath) {
        $Args += @("-PgRestorePath", $PgRestorePath)
    }
    if ($DryRun) {
        $Args += "-DryRun"
    }
    return $Args
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$FileName = "product-monitor-$Stamp.dump"

Write-Host "Scheduled backup plan:" -ForegroundColor Cyan
Write-Host "  env_path=$EnvPath"
Write-Host "  output_dir=$OutputDir"
Write-Host "  file_name=$FileName"
Write-Host "  keep_last=$KeepLast"

& powershell (Backup-Arguments $FileName)
if ($LASTEXITCODE -ne 0) {
    throw "backup-database.ps1 failed with exit code $LASTEXITCODE"
}

if ($DryRun) {
    Write-Host "Dry run complete; retention cleanup was not applied." -ForegroundColor Yellow
    exit 0
}

$Backups = Get-ChildItem -Path $OutputDir -Filter "product-monitor-*.dump" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
$Delete = $Backups | Select-Object -Skip $KeepLast

foreach ($File in $Delete) {
    Remove-Item -LiteralPath $File.FullName
    Write-Host "Deleted old backup: $($File.FullName)" -ForegroundColor Yellow
}

Write-Host "Scheduled backup complete. kept=$([Math]::Min($Backups.Count, $KeepLast)) deleted=$($Delete.Count)" -ForegroundColor Green
