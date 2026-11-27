# eHadiPanel web (local) - one-time setup + run, all in PowerShell
#   .\setup_web.ps1                  install (venv + packages + folders)
#   .\setup_web.ps1 -Run             install if needed, then start the server
#   .\setup_web.ps1 -AddAdmin        create the first admin (asks for password)
#   .\setup_web.ps1 -Run -Lan        run reachable on the local network
param([switch]$Run, [switch]$AddAdmin, [switch]$Lan, [int]$Port = 8000, [switch]$Test)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
[Console]::OutputEncoding = [Text.Encoding]::UTF8

function Find-Python {
    foreach ($c in @(@("py","-3"), @("python"), @("python3"))) {
        try {
            $v = & $c[0] $c[1..($c.Count)] -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.10") { return ,$c }
        } catch {}
    }
    return $null
}

$venvPy = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    $py = Find-Python
    if (-not $py) {
        Write-Host "Python 3.10+ not found. Installing 3.12 with winget..." -ForegroundColor Yellow
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        Write-Host "Close this window, open a NEW PowerShell and run the script again." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "[1/3] Creating venv..." -ForegroundColor Cyan
    & $py[0] $py[1..($py.Count)] -m venv venv
}
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) { Copy-Item .env.example .env }
foreach ($d in "data","data\raw_docs","data\duckdb","data\lancedb","data\storage","backups","logs") { New-Item -ItemType Directory -Force $d | Out-Null }

$marker = "venv\.deps_ok"
$reqHash = (Get-FileHash requirements.txt).Hash
if (-not (Test-Path $marker) -or (Get-Content $marker) -ne $reqHash) {
    Write-Host "[2/3] Installing packages (first time takes a few minutes)..." -ForegroundColor Cyan
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install --prefer-binary -r requirements.txt
    $reqHash | Set-Content $marker
}
& $venvPy -c "import duckdb, lancedb, pandas, openpyxl, docx, pptx, pymupdf, starlette, uvicorn; print('imports OK')"

if ($Test) {
    & $venvPy -m pip install -q -r requirements-dev.txt
    & $venvPy -m pytest -q tests
    exit $LASTEXITCODE
}
if ($AddAdmin) {
    $u = Read-Host "admin username"
    $n = Read-Host "display name"
    & $venvPy manage_users.py add $u $n admin
}
if ($Run) {
    & $venvPy manage_users.py list | Out-Null
    $runArgs = @("run_web.py","--port",$Port); if ($Lan) { $runArgs += "--lan" }
    Write-Host "[3/3] Starting on http://127.0.0.1:$Port  (Ctrl+C to stop)" -ForegroundColor Green
    & $venvPy @runArgs
} elseif (-not $AddAdmin) {
    Write-Host "Setup done. Next: .\setup_web.ps1 -AddAdmin   then   .\setup_web.ps1 -Run" -ForegroundColor Green
}
