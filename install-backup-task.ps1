param(
    [string]$DatabaseUrl,
    [string]$EnvPath = ".env",
    [string]$TaskName = "ProductMonitor-DatabaseBackup",
    [string]$OutputDir = "backups",
    [int]$KeepLast = 14,
    [string]$At = "03:20",
    [switch]$Elevated,
    [switch]$Register,
    [switch]$StartAfterRegister,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not [System.IO.Path]::IsPathRooted($EnvPath)) {
    $EnvPath = Join-Path $Root $EnvPath
}

if (-not $DatabaseUrl -and -not (Test-Path $EnvPath)) {
    throw "EnvPath was not found and DatabaseUrl was not provided: $EnvPath"
}

if ($KeepLast -lt 1) {
    throw "KeepLast must be at least 1."
}

function Quote-Arg([string]$Value) {
    '"' + $Value.Replace('"', '\"') + '"'
}

$ScriptPath = Join-Path $Root "run-scheduled-backup.ps1"
if (-not (Test-Path $ScriptPath)) {
    throw "Script not found: $ScriptPath"
}

$BackupArgs = @(
    "-NoProfile",
    "-ExecutionPolicy Bypass",
    "-File $(Quote-Arg $ScriptPath)",
    "-EnvPath $(Quote-Arg $EnvPath)",
    "-OutputDir $(Quote-Arg $OutputDir)",
    "-KeepLast $KeepLast"
)
if ($DatabaseUrl) {
    $BackupArgs += "-DatabaseUrl $(Quote-Arg $DatabaseUrl)"
}
$Arguments = $BackupArgs -join " "

Write-Host "Backup task plan:" -ForegroundColor Cyan
Write-Host "  TaskName: $TaskName"
Write-Host "  EnvPath: $EnvPath"
Write-Host "  Schedule: daily at $At"
Write-Host "  RunLevel: $(if ($Elevated) { 'Highest' } else { 'Limited' })"
Write-Host "  Script: $ScriptPath"
Write-Host "  Args: $Arguments"

if ($DryRun -or -not $Register) {
    Write-Host "Dry run complete; backup task was not registered." -ForegroundColor Yellow
    Write-Host "Add -Register to create or update the backup task."
    exit 0
}

$Trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact($At, "HH:mm", $null))
$RunLevel = if ($Elevated) { "Highest" } else { "Limited" }
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel $RunLevel
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Arguments -WorkingDirectory $Root

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Force | Out-Null
} catch {
    Write-Host "Failed to register $TaskName." -ForegroundColor Red
    Write-Host "Run this script from an administrator PowerShell, or review local Task Scheduler permissions." -ForegroundColor Yellow
    Write-Host "Use -Elevated only if you explicitly need RunLevel Highest." -ForegroundColor Yellow
    throw
}

Write-Host "Registered $TaskName" -ForegroundColor Green

if ($StartAfterRegister) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started $TaskName" -ForegroundColor Green
}
