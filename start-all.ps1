$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$pythonExe = Join-Path $backendDir "venv\Scripts\python.exe"
$npmCmd = "npm.cmd"
$backendUrl = "http://127.0.0.1:8000"
$frontendUrl = "http://127.0.0.1:5173"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Virtual environment Python was not found: $pythonExe"
}

if (-not (Test-Path $frontendDir)) {
    Write-Error "Frontend directory was not found: $frontendDir"
}

function Test-PortListening {
    param([int]$Port)

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $connection
}

Write-Host "[1/2] Starting FastAPI backend..." -ForegroundColor Cyan
if (Test-PortListening -Port 8000) {
    Write-Host "FastAPI backend is already running on port 8000." -ForegroundColor Green
} else {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$backendDir'; & '$pythonExe' '-m' 'uvicorn' 'app:app' '--host' '127.0.0.1' '--port' '8000' '--reload'"
    ) | Out-Null
    Start-Sleep -Seconds 2
}

Write-Host "[2/2] Starting React frontend..." -ForegroundColor Cyan
if (Test-PortListening -Port 5173) {
    Write-Host "React frontend is already running on port 5173." -ForegroundColor Green
} else {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$frontendDir'; & '$npmCmd' 'run' 'dev' '--' '--host' '127.0.0.1' '--port' '5173' '--strictPort'"
    ) | Out-Null
    Start-Sleep -Seconds 4
}

Write-Host ""
Write-Host "Backend URL : $backendUrl" -ForegroundColor Green
Write-Host "Frontend URL: $frontendUrl" -ForegroundColor Green

Start-Process $frontendUrl | Out-Null
