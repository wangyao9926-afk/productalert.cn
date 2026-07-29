param(
    [ValidateSet("status", "start", "stop", "delete")]
    [string]$Action = "status",
    [string]$TaskPrefix = "ProductMonitor",
    [switch]$DryRun,
    [switch]$ConfirmDelete
)

$ErrorActionPreference = "Stop"

$TaskNames = @(
    "$TaskPrefix-API",
    "$TaskPrefix-RQWorker",
    "$TaskPrefix-NotificationWorker",
    "$TaskPrefix-DatabaseBackup"
)

function Get-ManagedTask([string]$TaskName) {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

function Show-TaskStatus([string]$TaskName) {
    $Task = Get-ManagedTask $TaskName
    if (-not $Task) {
        Write-Host "$TaskName missing" -ForegroundColor Yellow
        return
    }

    $Info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    $LastRunTime = if ($Info) { $Info.LastRunTime } else { "" }
    $LastTaskResult = if ($Info) { $Info.LastTaskResult } else { "" }
    Write-Host "$TaskName state=$($Task.State) last_run=$LastRunTime result=$LastTaskResult"
}

function Invoke-TaskAction([string]$TaskName, [string]$Verb) {
    $Task = Get-ManagedTask $TaskName
    if (-not $Task) {
        Write-Host "$TaskName missing" -ForegroundColor Yellow
        return
    }

    if ($DryRun) {
        Write-Host "Would $Verb $TaskName" -ForegroundColor Yellow
        return
    }

    switch ($Verb) {
        "start" {
            Start-ScheduledTask -TaskName $TaskName
            Write-Host "Started $TaskName" -ForegroundColor Green
        }
        "stop" {
            Stop-ScheduledTask -TaskName $TaskName
            Write-Host "Stopped $TaskName" -ForegroundColor Green
        }
        "delete" {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "Deleted $TaskName" -ForegroundColor Green
        }
    }
}

if ($Action -eq "delete" -and -not $DryRun -and -not $ConfirmDelete) {
    throw "Refusing to delete scheduled tasks without -ConfirmDelete. Use -DryRun to preview."
}

Write-Host "Managing Windows tasks with prefix '$TaskPrefix' action '$Action'" -ForegroundColor Cyan

foreach ($TaskName in $TaskNames) {
    switch ($Action) {
        "status" { Show-TaskStatus $TaskName }
        "start" { Invoke-TaskAction $TaskName "start" }
        "stop" { Invoke-TaskAction $TaskName "stop" }
        "delete" { Invoke-TaskAction $TaskName "delete" }
    }
}
