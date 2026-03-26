$ErrorActionPreference = "Stop"

$portsToStop = @(8000, 5173)

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
            Write-Host "Stopping process on port ${Port}: $($process.ProcessName) (PID $processId)" -ForegroundColor Yellow
            Stop-Process -Id $processId -Force
        } catch {
            Write-Host "Could not stop process with PID $processId on port ${Port}." -ForegroundColor Red
        }
    }
}

foreach ($port in $portsToStop) {
    Stop-ListeningPort -Port $port
}
