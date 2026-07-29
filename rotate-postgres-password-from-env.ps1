param(
    [string]$EnvPath = ".env",
    [string]$AdminDatabaseUrl = "postgresql://postgres@127.0.0.1:5432/postgres",
    [string]$AdminPassword = "",
    [string]$RedisUrl = "redis://127.0.0.1:6379/0",
    [string]$PsqlPath = "",
    [switch]$RunDeployCheck,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not [System.IO.Path]::IsPathRooted($EnvPath)) {
    $EnvPath = Join-Path $Root $EnvPath
}

function Read-EnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path $Path)) {
        throw "EnvPath not found: $Path"
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
    throw "$Name was not found in $Path"
}

$DatabaseUrl = Read-EnvValue $EnvPath "DATABASE_URL"
if ($DatabaseUrl -notmatch "^(postgresql|postgres)://") {
    throw "DATABASE_URL in EnvPath must be PostgreSQL."
}
if ($DatabaseUrl -match "change-me|replace-with-strong-password|your-postgres-password") {
    throw "DATABASE_URL in EnvPath contains a placeholder password."
}

$Uri = [System.Uri]$DatabaseUrl
$User = [System.Uri]::UnescapeDataString($Uri.UserInfo.Split(":", 2)[0])
if (-not $User) {
    throw "DATABASE_URL must include a username."
}
if ($Uri.UserInfo.Split(":", 2).Count -lt 2) {
    throw "DATABASE_URL must include a password."
}
$Password = [System.Uri]::UnescapeDataString($Uri.UserInfo.Split(":", 2)[1])
$DatabaseName = $Uri.AbsolutePath.TrimStart("/")

$Args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $Root "rotate-postgres-app-password.ps1"),
    "-AdminDatabaseUrl", $AdminDatabaseUrl,
    "-AppDatabaseName", $DatabaseName,
    "-AppUser", $User,
    "-NewPassword", $Password,
    "-RedisUrl", $RedisUrl
)
if ($AdminPassword) {
    $Args += @("-AdminPassword", $AdminPassword)
}
if ($PsqlPath) {
    $Args += @("-PsqlPath", $PsqlPath)
}
if ($RunDeployCheck) {
    $Args += "-RunDeployCheck"
}
if ($Apply) {
    $Args += "-Apply"
}

& powershell @Args

if ($LASTEXITCODE -ne 0) {
    throw "rotate-postgres-app-password.ps1 failed with exit code $LASTEXITCODE"
}
