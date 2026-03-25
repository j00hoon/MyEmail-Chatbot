$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$pythonExe = Join-Path $backendDir "venv\Scripts\python.exe"
$npmCmd = "npm.cmd"
$redisContainerName = "redis"
$backendUrl = "http://127.0.0.1:5000"
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

Write-Host "[1/3] Preparing Redis..." -ForegroundColor Cyan
$redisContainerId = docker ps -aq -f "name=^${redisContainerName}$"

if (-not $redisContainerId) {
    Write-Host "Redis container does not exist. Creating a new one..." -ForegroundColor Yellow
    docker run -d --name $redisContainerName -p 6379:6379 redis | Out-Null
} else {
    $redisRunning = docker ps -q -f "name=^${redisContainerName}$"
    if (-not $redisRunning) {
        Write-Host "Starting existing Redis container..." -ForegroundColor Yellow
        docker start $redisContainerName | Out-Null
    } else {
        Write-Host "Redis container is already running." -ForegroundColor Green
    }
}

Write-Host "[2/3] Starting Flask backend..." -ForegroundColor Cyan
if (Test-PortListening -Port 5000) {
    Write-Host "Flask backend is already running on port 5000." -ForegroundColor Green
} else {
    Write-Host "Using virtual environment Python: $pythonExe" -ForegroundColor DarkGray
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$backendDir'; & '$pythonExe' 'app.py'"
    ) | Out-Null
    Start-Sleep -Seconds 2
}

Write-Host "[3/3] Starting React frontend..." -ForegroundColor Cyan
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
Write-Host "Opening the frontend in your browser..." -ForegroundColor Cyan

Start-Process $frontendUrl | Out-Null
