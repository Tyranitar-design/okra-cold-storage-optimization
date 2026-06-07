param(
    [int]$Port = 8014,
    [string]$HostAddress = "127.0.0.1",
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

# --- Gurobi NODE license ---
$env:GRB_LICENSE_FILE = "D:\Gurobi1300\win64\bin\gurobi.lic"

# --- Resolve runtime config via a Python helper ---
# Windows PowerShell 5.1 mojibakes CJK string literals in a BOM-less .ps1, so we
# delegate secret/interpreter resolution to scripts/resolve_demo_config.py, which
# reads UTF-8 paths reliably. It emits KEY=VALUE lines (DB URL + AMap keys +
# UNIFIED_PYTHON). Secret values are applied to the environment and never logged.
$Python = "python"
$resolverPy = $null
foreach ($p in @("C:\Python314\python.exe", "python")) {
    if ($p.EndsWith(".exe")) {
        if (Test-Path -LiteralPath $p) {
            $resolverPy = $p
            break
        }
        continue
    }

    $cmd = Get-Command $p -ErrorAction SilentlyContinue
    if ($cmd) {
        $resolverPy = $cmd.Source
        break
    }
}

if (-not $resolverPy) {
    throw "No Python interpreter found for resolve_demo_config.py"
}

$configLines = & $resolverPy (Join-Path $ProjectRoot "scripts\resolve_demo_config.py") 2>$null
foreach ($line in $configLines) {
    if ($line -match '^\s*([A-Z_]+)=(.*)$') {
        $name = $Matches[1]
        $value = $Matches[2]
        if ($name -eq "UNIFIED_PYTHON") {
            if (Test-Path -LiteralPath $value) { $Python = $value }
        } elseif (-not [string]::IsNullOrWhiteSpace($value)) {
            # Do not overwrite a DB URL the caller pre-set.
            if ($name -eq "OKRA_DATABASE_URL" -and $env:OKRA_DATABASE_URL) { continue }
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

# --- Status (booleans only; never print secret values) ---
if ($env:OKRA_DATABASE_URL) {
    Write-Host "OKRA_DATABASE_URL configured (okra@localhost:5432/okra_cold_storage)" -ForegroundColor Green
} else {
    Write-Host "OKRA_DATABASE_URL not set; API will use file fallback." -ForegroundColor Yellow
}
if ($env:OKRA_AMAP_JS_KEY -and $env:OKRA_MAP_PUBLIC_KEY_ALLOWED -eq "true") {
    Write-Host "AMap browser basemap enabled (provider=$($env:OKRA_MAP_PROVIDER), key configured)" -ForegroundColor Green
} else {
    Write-Host "AMap JS key not enabled; map will use file point fallback." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Okra cold storage MIS demo"
Write-Host "Project root: $ProjectRoot"
Write-Host "Python:       $Python"
Write-Host "API:          http://$HostAddress`:$Port"
Write-Host "Frontend:     http://$HostAddress`:$Port/app"
Write-Host ""

$uvicornArgs = [System.Collections.ArrayList]@(
    "-m", "uvicorn", "src.api.main:app",
    "--host", $HostAddress,
    "--port", "$Port"
)
if (-not $NoReload) { [void]$uvicornArgs.Add("--reload") }
& $Python @uvicornArgs
