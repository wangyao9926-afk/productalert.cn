param(
    [string]$DatabaseUrl,
    [string]$EnvPath = ".env",
    [string]$RedisUrl = "",
    [string]$TaskPrefix = "ProductMonitor",
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 8000,
    [string]$LogDir = "",
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

if (-not $LogDir) {
    $LogDir = Join-Path $Root "logs"
} elseif (-not [System.IO.Path]::IsPathRooted($LogDir)) {
    $LogDir = Join-Path $Root $LogDir
}

if (-not $DatabaseUrl -and -not (Test-Path $EnvPath)) {
    throw "EnvPath was not found and DatabaseUrl was not provided: $EnvPath"
}

function Quote-Arg([string]$Value) {
    '"' + $Value.Replace('"', '\"') + '"'
}

function New-TaskDefinition([string]$Name, [string]$Script, [string]$Arguments) {
    $ScriptPath = Join-Path $Root $Script
    if (-not (Test-Path $ScriptPath)) {
        throw "Script not found: $ScriptPath"
    }
    [pscustomobject]@{
        Name = "$TaskPrefix-$Name"
        ScriptPath = $ScriptPath
        Arguments = $Arguments
    }
}

$Tasks = @()
$ApiArgs = @(
    "-EnvPath $(Quote-Arg $EnvPath)",
    "-Queue rq",
    "-HostName $(Quote-Arg $ApiHost)",
    "-Port $ApiPort",
    "-LogDir $(Quote-Arg $LogDir)"
)
$RqArgs = @(
    "-EnvPath $(Quote-Arg $EnvPath)",
    "-LogDir $(Quote-Arg $LogDir)"
)
$NotificationArgs = @(
    "-EnvPath $(Quote-Arg $EnvPath)",
    "-LogDir $(Quote-Arg $LogDir)"
)
if ($DatabaseUrl) {
    $ApiArgs += "-DatabaseUrl $(Quote-Arg $DatabaseUrl)"
    $RqArgs += "-DatabaseUrl $(Quote-Arg $DatabaseUrl)"
    $NotificationArgs += "-DatabaseUrl $(Quote-Arg $DatabaseUrl)"
}
if ($RedisUrl) {
    $ApiArgs += "-RedisUrl $(Quote-Arg $RedisUrl)"
    $RqArgs += "-RedisUrl $(Quote-Arg $RedisUrl)"
}
$Tasks += New-TaskDefinition `
    -Name "API" `
    -Script "start-api-production.ps1" `
    -Arguments ($ApiArgs -join " ")
$Tasks += New-TaskDefinition `
    -Name "RQWorker" `
    -Script "start-rq-worker.ps1" `
    -Arguments ($RqArgs -join " ")
$Tasks += New-TaskDefinition `
    -Name "NotificationWorker" `
    -Script "start-notification-worker.ps1" `
    -Arguments ($NotificationArgs -join " ")

Write-Host "Windows task plan:" -ForegroundColor Cyan
Write-Host "  EnvPath: $EnvPath"
Write-Host "  LogDir: $LogDir"
Write-Host "  RunLevel: $(if ($Elevated) { 'Highest' } else { 'Limited' })"
foreach ($Task in $Tasks) {
    Write-Host "  $($Task.Name)"
    Write-Host "    Script: $($Task.ScriptPath)"
    Write-Host "    Args: $($Task.Arguments)"
}

if ($DryRun -or -not $Register) {
    Write-Host "Dry run complete; no tasks were registered." -ForegroundColor Yellow
    Write-Host "Add -Register to create or update scheduled tasks."
    exit 0
}

$RunLevel = if ($Elevated) { "Highest" } else { "Limited" }
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel $RunLevel
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 30)

foreach ($Task in $Tasks) {
    $Argument = "-NoProfile -ExecutionPolicy Bypass -File $(Quote-Arg $Task.ScriptPath)"
    if ($Task.Arguments) {
        $Argument = "$Argument $($Task.Arguments)"
    }
    $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Argument -WorkingDirectory $Root
    try {
        Register-ScheduledTask `
            -TaskName $Task.Name `
            -Action $Action `
            -Trigger $Trigger `
            -Principal $Principal `
            -Settings $Settings `
            -Force | Out-Null
    } catch {
        Write-Host "Failed to register $($Task.Name)." -ForegroundColor Red
        Write-Host "Run this script from an administrator PowerShell, or review local Task Scheduler permissions." -ForegroundColor Yellow
        Write-Host "Use -Elevated only if you explicitly need RunLevel Highest." -ForegroundColor Yellow
        throw
    }
    Write-Host "Registered $($Task.Name)" -ForegroundColor Green
    if ($StartAfterRegister) {
        Start-ScheduledTask -TaskName $Task.Name
        Write-Host "Started $($Task.Name)" -ForegroundColor Green
    }
}
