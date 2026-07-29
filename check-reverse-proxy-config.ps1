param(
    [Parameter(Mandatory=$true)]
    [string]$Domain,
    [string]$EnvPath = ".env",
    [string]$BackendUrl = "http://127.0.0.1:8000/api/system/ping",
    [string]$CaddyfilePath = "Caddyfile.example",
    [string]$CaddyPath = "",
    [switch]$SkipBackend,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not [System.IO.Path]::IsPathRooted($EnvPath)) {
    $EnvPath = Join-Path $Root $EnvPath
}
if (-not [System.IO.Path]::IsPathRooted($CaddyfilePath)) {
    $CaddyfilePath = Join-Path $Root $CaddyfilePath
}

$Failures = 0
$Warnings = 0

function Add-Failure([string]$Message) {
    $script:Failures += 1
    Write-Host "[fail] $Message" -ForegroundColor Red
}

function Add-Warning([string]$Message) {
    $script:Warnings += 1
    Write-Host "[warn] $Message" -ForegroundColor Yellow
}

function Add-Ok([string]$Message) {
    Write-Host "[ok] $Message" -ForegroundColor Green
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

Write-Host "Reverse proxy readiness check:" -ForegroundColor Cyan
Write-Host "  Domain=$Domain"
Write-Host "  EnvPath=$EnvPath"
Write-Host "  BackendUrl=$BackendUrl"
Write-Host "  CaddyfilePath=$CaddyfilePath"
Write-Host "  CaddyPath=$CaddyPath"

if ($Domain -match "^(localhost|127\.0\.0\.1|example\.com|monitor\.example\.com)$") {
    Add-Failure "Domain must be a real public hostname, not $Domain"
} elseif ($Domain -notmatch "^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$") {
    Add-Failure "Domain is not a valid hostname"
} else {
    Add-Ok "domain format looks valid"
}

if (-not (Test-Path $EnvPath)) {
    Add-Failure "EnvPath was not found"
} else {
    Add-Ok "env file exists"
    $CookieSecure = Read-EnvValue $EnvPath "SESSION_COOKIE_SECURE"
    if ($CookieSecure -ne "true") {
        Add-Failure "SESSION_COOKIE_SECURE must be true behind HTTPS"
    } else {
        Add-Ok "SESSION_COOKIE_SECURE=true"
    }
}

if ($SkipBackend) {
    Add-Warning "backend API reachability skipped"
} else {
    try {
        $Response = Invoke-RestMethod -Uri $BackendUrl -TimeoutSec 5
        $Status = if ($Response.status) { $Response.status } else { "response_received" }
        Add-Ok "backend API reachable status=$Status"
    } catch {
        Add-Failure "backend API is not reachable at ${BackendUrl}: $($_.Exception.Message)"
    }
}

if (-not (Test-Path $CaddyfilePath)) {
    Add-Failure "CaddyfilePath was not found"
} else {
    $Caddyfile = Get-Content -Path $CaddyfilePath -Raw
    if ($Caddyfile -notmatch "reverse_proxy\s+127\.0\.0\.1:8000") {
        Add-Failure "Caddyfile must reverse_proxy 127.0.0.1:8000"
    } else {
        Add-Ok "Caddyfile reverse proxy target is local API"
    }
    if ($Caddyfile -notmatch "Strict-Transport-Security") {
        Add-Warning "Caddyfile does not set HSTS"
    } else {
        Add-Ok "Caddyfile includes HSTS"
    }
}

$CaddySource = ""
if ($CaddyPath) {
    if (Test-Path $CaddyPath) {
        $CaddySource = $CaddyPath
    } else {
        Add-Failure "CaddyPath was not found: $CaddyPath"
    }
} else {
    $Caddy = Get-Command caddy -ErrorAction SilentlyContinue
    if ($Caddy) {
        $CaddySource = $Caddy.Source
    }
}

if ($CaddySource) {
    Add-Ok "caddy executable found at $CaddySource"
    try {
        & $CaddySource validate --config $CaddyfilePath | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Add-Ok "caddy validate passed"
        } else {
            Add-Failure "caddy validate failed with exit code $LASTEXITCODE"
        }
    } catch {
        Add-Failure "caddy validate failed: $($_.Exception.Message)"
    }
} else {
    Add-Warning "caddy executable not found; install Caddy before public HTTPS launch"
}

Write-Host "Reverse proxy readiness summary: failures=$Failures warnings=$Warnings" -ForegroundColor Cyan
if ($Failures -gt 0 -or ($Strict -and $Warnings -gt 0)) {
    exit 1
}
