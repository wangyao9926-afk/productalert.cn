param(
    [string]$AdminDatabaseUrl = "postgresql://postgres@localhost:5432/postgres",
    [string]$AdminPassword = "",
    [string]$AppDatabaseName = "product_monitor",
    [string]$AppUser = "product_monitor",
    [Parameter(Mandatory=$true)]
    [string]$NewPassword,
    [string]$RedisUrl = "redis://127.0.0.1:6379/0",
    [string]$PsqlPath = "",
    [switch]$RunDeployCheck,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeployCheck = Join-Path $Root "deploy-check.ps1"

function Assert-SafeIdentifier([string]$Value, [string]$Label) {
    if ($Value -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "$Label must contain only letters, numbers, and underscores, and must not start with a number."
    }
}

function Quote-Identifier([string]$Value) {
    '"' + $Value.Replace('"', '""') + '"'
}

function Quote-Literal([string]$Value) {
    "'" + $Value.Replace("'", "''") + "'"
}

function App-Database-Url {
    $UserEscaped = [System.Uri]::EscapeDataString($AppUser)
    $PasswordEscaped = [System.Uri]::EscapeDataString($NewPassword)
    return "postgresql://${UserEscaped}:${PasswordEscaped}@127.0.0.1:5432/$AppDatabaseName"
}

function Redacted-App-Database-Url {
    $UserEscaped = [System.Uri]::EscapeDataString($AppUser)
    return "postgresql://${UserEscaped}:<redacted>@127.0.0.1:5432/$AppDatabaseName"
}

if ($NewPassword.Length -lt 16) {
    throw "NewPassword must be at least 16 characters."
}
if ($NewPassword -eq "change-me") {
    throw "NewPassword must not be the default placeholder."
}

Assert-SafeIdentifier $AppDatabaseName "AppDatabaseName"
Assert-SafeIdentifier $AppUser "AppUser"

$UserIdent = Quote-Identifier $AppUser
$PasswordLiteral = Quote-Literal $NewPassword
$ResolvedAppDatabaseUrl = App-Database-Url
$RedactedAppDatabaseUrl = Redacted-App-Database-Url
$Sql = "ALTER ROLE $UserIdent WITH LOGIN PASSWORD $PasswordLiteral;"

$PsqlCommand = $null
if ($PsqlPath) {
    if (-not (Test-Path $PsqlPath)) {
        throw "PsqlPath was not found: $PsqlPath"
    }
    $PsqlCommand = $PsqlPath
} else {
    $Psql = Get-Command psql -ErrorAction SilentlyContinue
    if ($Psql) {
        $PsqlCommand = $Psql.Source
    } else {
        $KnownPaths = @(
            "C:\Program Files\PostgreSQL\18\bin\psql.exe",
            "C:\Program Files\PostgreSQL\17\bin\psql.exe",
            "C:\Program Files\PostgreSQL\16\bin\psql.exe"
        )
        foreach ($Path in $KnownPaths) {
            if (Test-Path $Path) {
                $PsqlCommand = $Path
                break
            }
        }
    }
}

if (-not $PsqlCommand) {
    throw "psql was not found. Pass -PsqlPath or add PostgreSQL bin directory to PATH."
}

Write-Host "PostgreSQL app password rotation plan:" -ForegroundColor Cyan
Write-Host "  AdminDatabaseUrl=$AdminDatabaseUrl"
Write-Host "  AppUser=$AppUser"
Write-Host "  AppDatabaseName=$AppDatabaseName"
Write-Host "  psql=$PsqlCommand"
Write-Host "  NewDatabaseUrl=$RedactedAppDatabaseUrl"
Write-Host "  Apply=$Apply"

if (-not $Apply) {
    Write-Host "Dry run complete; password was not changed." -ForegroundColor Yellow
    Write-Host "Rerun with -Apply to rotate the password."
    exit 0
}

$PreviousPgPassword = $env:PGPASSWORD
try {
    if ($AdminPassword) {
        $env:PGPASSWORD = $AdminPassword
        & $PsqlCommand $AdminDatabaseUrl -v ON_ERROR_STOP=1 -c $Sql
    } else {
        & $PsqlCommand -w $AdminDatabaseUrl -v ON_ERROR_STOP=1 -c $Sql
    }
    if ($LASTEXITCODE -ne 0) {
        throw "psql failed with exit code $LASTEXITCODE"
    }
    Write-Host "PostgreSQL app password rotated." -ForegroundColor Green
    Write-Host "DATABASE_URL=$RedactedAppDatabaseUrl"

    if ($RunDeployCheck) {
        if (-not (Test-Path $DeployCheck)) {
            throw "deploy-check.ps1 was not found."
        }
        & powershell -ExecutionPolicy Bypass -File $DeployCheck `
            -Backend postgresql `
            -Queue rq `
            -DatabaseUrl $ResolvedAppDatabaseUrl `
            -RedisUrl $RedisUrl
    }
} finally {
    $env:PGPASSWORD = $PreviousPgPassword
}
