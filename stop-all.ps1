$ErrorActionPreference = "Stop"

$redisContainerName = "redis"
$portsToStop = @(5000, 5173)

function Stop-ListeningPort {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue

    if (-not $connections) {
        Write-Host "No listening process found on port $Port." -ForegroundColor DarkGray
        return
    }

    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            Write-Host "Stopping process on port $Port: $($process.ProcessName) (PID $processId)" -ForegroundColor Yellow
            Stop-Process -Id $processId -Force
        } catch {
            Write-Host "Could not stop process with PID $processId on port $Port." -ForegroundColor Red
        }
    }
}

Write-Host "[1/3] Stopping frontend and backend processes..." -ForegroundColor Cyan
foreach ($port in $portsToStop) {
    Stop-ListeningPort -Port $port
}

Write-Host "[2/3] Stopping Redis container..." -ForegroundColor Cyan
$redisRunning = docker ps -q -f "name=^${redisContainerName}$"
if ($redisRunning) {
    docker stop $redisContainerName | Out-Null
    Write-Host "Redis container stopped." -ForegroundColor Green
} else {
    Write-Host "Redis container is not running." -ForegroundColor DarkGray
}

Write-Host "[3/3] Done." -ForegroundColor Green
