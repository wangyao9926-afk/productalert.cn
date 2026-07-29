param(
    [string]$LogDir = "logs",
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not [System.IO.Path]::IsPathRooted($LogDir)) {
    $LogDir = Join-Path $Root $LogDir
}

if (-not (Test-Path $LogDir)) {
    throw "LogDir not found: $LogDir"
}

$Pattern = '(postgres(?:ql)?://[^:\s]+):([^@\s]+)@'
$Replacement = '$1:<redacted>@'
$FilesChanged = 0
$MatchesChanged = 0

Write-Host "Log secret redaction:" -ForegroundColor Cyan
Write-Host "  LogDir=$LogDir"
Write-Host "  Apply=$Apply"

Get-ChildItem -Path $LogDir -Filter "*.log" -File | ForEach-Object {
    $Path = $_.FullName
    $Content = Get-Content -LiteralPath $Path -Raw
    if ($null -eq $Content) {
        $Content = ""
    }
    $Matches = [regex]::Matches($Content, $Pattern)
    if ($Matches.Count -eq 0) {
        Write-Host "[ok] $($_.Name) no database URLs found"
        return
    }

    $FilesChanged += 1
    $MatchesChanged += $Matches.Count
    Write-Host "[redact] $($_.Name) matches=$($Matches.Count)" -ForegroundColor Yellow

    if ($Apply) {
        $Redacted = [regex]::Replace($Content, $Pattern, $Replacement)
        Set-Content -LiteralPath $Path -Value $Redacted -Encoding UTF8
    }
}

Write-Host "Log redaction summary: files=$FilesChanged matches=$MatchesChanged apply=$Apply" -ForegroundColor Cyan
if (-not $Apply) {
    Write-Host "Dry run only; rerun with -Apply to rewrite log files." -ForegroundColor Yellow
}
