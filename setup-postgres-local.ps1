param(
    [string]$AdminDatabaseUrl = "postgresql://postgres@localhost:5432/postgres",
    [string]$AdminPassword = "",
    [string]$AppDatabaseName = "product_monitor",
    [string]$AppUser = "product_monitor",
    [string]$AppPassword = "change-me",
    [string]$AppDatabaseUrl = "",
    [string]$RedisUrl = "redis://localhost:6379/0",
    [string]$PsqlPath = "",
    [switch]$RunDeployCheck,
    [switch]$PrintOnly
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
    if ($AppDatabaseUrl) {
        return $AppDatabaseUrl
    }
    $UserEscaped = [System.Uri]::EscapeDataString($AppUser)
    $PasswordEscaped = [System.Uri]::EscapeDataString($AppPassword)
    return "postgresql://${UserEscaped}:${PasswordEscaped}@localhost:5432/$AppDatabaseName"
}

function Redacted-App-Database-Url {
    if ($AppDatabaseUrl) {
        try {
            $Uri = [System.Uri]$AppDatabaseUrl
            if ($Uri.UserInfo -and $Uri.UserInfo.Contains(":")) {
                $User = $Uri.UserInfo.Split(":", 2)[0]
                return $AppDatabaseUrl.Replace($Uri.UserInfo, "${User}:<redacted>")
            }
        } catch {
            return "<redacted>"
        }
        return $AppDatabaseUrl
    }
    $UserEscaped = [System.Uri]::EscapeDataString($AppUser)
    return "postgresql://${UserEscaped}:<redacted>@localhost:5432/$AppDatabaseName"
}

function Invoke-PsqlFile([string]$Command, [string]$DatabaseUrl, [string]$SqlPath, [bool]$NoPasswordPrompt) {
    if ($NoPasswordPrompt) {
        & $Command -w $DatabaseUrl -v ON_ERROR_STOP=1 -f $SqlPath
    } else {
        & $Command $DatabaseUrl -v ON_ERROR_STOP=1 -f $SqlPath
    }
    if ($LASTEXITCODE -ne 0) {
        throw "psql failed with exit code $LASTEXITCODE"
    }
}

Assert-SafeIdentifier $AppDatabaseName "AppDatabaseName"
Assert-SafeIdentifier $AppUser "AppUser"

$DbIdent = Quote-Identifier $AppDatabaseName
$UserIdent = Quote-Identifier $AppUser
$UserLiteral = Quote-Literal $AppUser
$PasswordLiteral = Quote-Literal $AppPassword
$DbLiteral = Quote-Literal $AppDatabaseName
$CreateDatabaseSql = "CREATE DATABASE $DbIdent OWNER $UserIdent"
$CreateDatabaseLiteral = Quote-Literal $CreateDatabaseSql
$ResolvedAppDatabaseUrl = App-Database-Url
$RedactedAppDatabaseUrl = Redacted-App-Database-Url

$Sql = @"
DO `$do`$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $UserLiteral) THEN
        CREATE ROLE $UserIdent LOGIN PASSWORD $PasswordLiteral;
    ELSE
        ALTER ROLE $UserIdent WITH LOGIN PASSWORD $PasswordLiteral;
    END IF;
END
`$do`$;

SELECT $CreateDatabaseLiteral
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = $DbLiteral)\gexec

GRANT ALL PRIVILEGES ON DATABASE $DbIdent TO $UserIdent;
\connect $AppDatabaseName
GRANT ALL ON SCHEMA public TO $UserIdent;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $UserIdent;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $UserIdent;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO $UserIdent;
"@

if ($PrintOnly) {
    Write-Host "AdminDatabaseUrl=$AdminDatabaseUrl"
    Write-Host "AppDatabaseUrl=$RedactedAppDatabaseUrl"
    Write-Host ""
    Write-Host ($Sql.Replace($PasswordLiteral, "'<redacted>'"))
    exit 0
}

$PsqlCommand = $null
if ($PsqlPath) {
    if (-not (Test-Path $PsqlPath)) {
        throw "PsqlPath was not found: $PsqlPath"
    }
    $PsqlCommand = $PsqlPath
} else {
    $Psql = Get-Command psql -ErrorAction SilentlyContinue
    if (-not $Psql) {
        throw "psql was not found on PATH. Pass -PsqlPath or add PostgreSQL bin directory to PATH, then rerun this script."
    }
    $PsqlCommand = $Psql.Source
}

$TempSql = Join-Path $env:TEMP ("product-monitor-postgres-" + [guid]::NewGuid().ToString("N") + ".sql")
try {
    Set-Content -LiteralPath $TempSql -Value $Sql -Encoding UTF8
    Write-Host "Creating/updating PostgreSQL database and role..." -ForegroundColor Cyan
    $PreviousPgPassword = $env:PGPASSWORD
    if ($AdminPassword) {
        $env:PGPASSWORD = $AdminPassword
        Invoke-PsqlFile $PsqlCommand $AdminDatabaseUrl $TempSql $false
    } else {
        Invoke-PsqlFile $PsqlCommand $AdminDatabaseUrl $TempSql $true
    }
    if ($AdminPassword) {
        $env:PGPASSWORD = $PreviousPgPassword
    }
    Write-Host "PostgreSQL bootstrap completed." -ForegroundColor Green
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
    if ($AdminPassword) {
        $env:PGPASSWORD = $PreviousPgPassword
    }
    Remove-Item -LiteralPath $TempSql -ErrorAction SilentlyContinue
}
