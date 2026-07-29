param(
    [string]$EnvPath = ".env",
    [int]$BackupKeepLast = 14,
    [string]$BackupAt = "03:20",
    [switch]$SkipReleaseGate
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not [System.IO.Path]::IsPathRooted($EnvPath)) {
    $EnvPath = Join-Path $Root $EnvPath
}

function Fail([string]$Message) {
    Write-Host "[fail] $Message" -ForegroundColor Red
    exit 1
}

function Run-Step([string]$Name, [scriptblock]$Command) {
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Read-EnvValue([string]$Path, [string]$Name) {
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

function Captured-Step([scriptblock]$Command) {
    $Output = & $Command 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Host $Output
        throw "command failed with exit code $LASTEXITCODE"
    }
    return $Output
}

if (-not (Test-Path $EnvPath)) {
    Fail "EnvPath was not found: $EnvPath"
}

$DatabaseUrl = Read-EnvValue $EnvPath "DATABASE_URL"
if (-not $DatabaseUrl) {
    Fail "DATABASE_URL was not found in EnvPath"
}

$Password = ""
try {
    $Uri = [System.Uri]$DatabaseUrl
    if ($Uri.UserInfo -and $Uri.UserInfo.Contains(":")) {
        $Password = [System.Uri]::UnescapeDataString($Uri.UserInfo.Split(":", 2)[1])
    }
} catch {
    Fail "DATABASE_URL is not a valid URI"
}
if (-not $Password) {
    Fail "DATABASE_URL must include a password"
}

Write-Host "Pre-register Windows task check:" -ForegroundColor Cyan
Write-Host "  EnvPath=$EnvPath"
Write-Host "  BackupKeepLast=$BackupKeepLast"
Write-Host "  BackupAt=$BackupAt"

Run-Step "production config" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "check-production-config.ps1") -EnvPath $EnvPath
}

if (-not $SkipReleaseGate) {
    Run-Step "release gate and backup dry-run" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "preflight-production.ps1") `
            -EnvPath $EnvPath `
            -SkipApi `
            -SkipHealthCheck `
            -BackupKeepLast $BackupKeepLast
    }
}

Run-Step "task dry-run" {
    $Output = Captured-Step {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "install-windows-tasks.ps1") `
            -DryRun `
            -EnvPath $EnvPath
    }
    if ($Output.Contains($Password)) {
        throw "install-windows-tasks.ps1 dry-run output contains the database password"
    }
    if ($Output -match "-DatabaseUrl") {
        throw "install-windows-tasks.ps1 dry-run embeds DatabaseUrl"
    }
    Write-Host $Output
}

Run-Step "backup task dry-run" {
    $Output = Captured-Step {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "install-backup-task.ps1") `
            -DryRun `
            -EnvPath $EnvPath `
            -KeepLast $BackupKeepLast `
            -At $BackupAt
    }
    if ($Output.Contains($Password)) {
        throw "install-backup-task.ps1 dry-run output contains the database password"
    }
    if ($Output -match "-DatabaseUrl") {
        throw "install-backup-task.ps1 dry-run embeds DatabaseUrl"
    }
    Write-Host $Output
}

Write-Host ""
Write-Host "Open Windows PowerShell as Administrator, then run:" -ForegroundColor Yellow
Write-Host "cd `"$Root`""
Write-Host ".\install-windows-tasks.ps1 -Register -StartAfterRegister -EnvPath .\.env"
Write-Host ".\install-backup-task.ps1 -Register -EnvPath .\.env -KeepLast $BackupKeepLast -At $BackupAt"
Write-Host ""
Write-Host "Pre-register Windows task check completed." -ForegroundColor Green
