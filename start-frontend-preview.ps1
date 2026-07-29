$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontend = Join-Path $root 'frontend'
$port = 4173
$previewUrl = "http://127.0.0.1:$port/overview"

function Test-Preview {
  try {
    $response = Invoke-WebRequest -UseBasicParsing $previewUrl -TimeoutSec 3
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
  if (Test-Preview) {
    Write-Host "Frontend preview already running at $previewUrl"
    exit 0
  }

  $owners = ($listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
  throw "Port $port is occupied by process id(s): $owners, but $previewUrl did not return HTTP 200."
}

$node = (Get-Command node.exe).Source
$vite = Join-Path $frontend 'node_modules/vite/bin/vite.js'
$stdout = Join-Path $frontend 'vite-preview.log'
$stderr = Join-Path $frontend 'vite-preview.err.log'

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match [regex]::Escape($vite) } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
  }

Start-Process -FilePath $node `
  -ArgumentList $vite, '--host', '127.0.0.1', '--port', $port, '--strictPort' `
  -WorkingDirectory $frontend `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden | Out-Null

for ($i = 0; $i -lt 20; $i++) {
  if (Test-Preview) {
    Write-Host "Frontend preview ready at $previewUrl"
    exit 0
  }
  Start-Sleep -Milliseconds 500
}

throw "Frontend preview failed to start at $previewUrl. See $stderr"
