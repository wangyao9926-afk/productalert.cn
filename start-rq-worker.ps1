param(
  [string]$DatabaseUrl = "",
  [string]$EnvPath = ".env",
  [string]$RedisUrl = "",
  [string]$LogDir = "logs",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

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

function Redact-Database-Url([string]$Value) {
  if (-not $Value) {
    return ""
  }
  try {
    $Uri = [System.Uri]$Value
    if ($Uri.UserInfo -and $Uri.UserInfo.Contains(":")) {
      $User = $Uri.UserInfo.Split(":", 2)[0]
      return $Value.Replace($Uri.UserInfo, "${User}:<redacted>")
    }
  } catch {
    return "<redacted>"
  }
  return $Value
}

if (-not (Test-Path $Python)) {
  Write-Host "Virtual environment not found. Create it with start.ps1 or install requirements first."
  exit 1
}

$env:QUEUE_BACKEND = "rq"
if ($DatabaseUrl) {
  $env:DATABASE_URL = $DatabaseUrl
} elseif (-not $env:DATABASE_URL) {
  $EnvDatabaseUrl = Read-EnvValue $EnvPath "DATABASE_URL"
  if ($EnvDatabaseUrl) {
    $env:DATABASE_URL = $EnvDatabaseUrl
  }
}
if ($RedisUrl) {
  $env:REDIS_URL = $RedisUrl
} elseif (Read-EnvValue $EnvPath "REDIS_URL") {
  $env:REDIS_URL = Read-EnvValue $EnvPath "REDIS_URL"
} elseif (-not $env:REDIS_URL) {
  $env:REDIS_URL = "redis://localhost:6379/0"
}

$ResolvedLogDir = ""
if ($LogDir) {
  if ([System.IO.Path]::IsPathRooted($LogDir)) {
    $ResolvedLogDir = $LogDir
  } else {
    $ResolvedLogDir = Join-Path $Root $LogDir
  }
}

$TranscriptStarted = $false
if (-not $DryRun -and $ResolvedLogDir) {
  New-Item -ItemType Directory -Force -Path $ResolvedLogDir | Out-Null
  Start-Transcript -Path (Join-Path $ResolvedLogDir "rq-worker.log") -Append | Out-Null
  $TranscriptStarted = $true
}

Write-Host "Starting RQ scan worker on $env:REDIS_URL"
Write-Host "  ENV_PATH=$EnvPath"
Write-Host "  DATABASE_URL=$(Redact-Database-Url $env:DATABASE_URL)"
Write-Host "  LOG_DIR=$ResolvedLogDir"

if ($DryRun) {
  Write-Host "Dry run complete; RQ worker was not started." -ForegroundColor Yellow
  exit 0
}

try {
  & $Python -m app.rq_worker
} finally {
  if ($TranscriptStarted) {
    Stop-Transcript | Out-Null
  }
}
