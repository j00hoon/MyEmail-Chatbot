$ErrorActionPreference = "Stop"

$portsToStop = @(8000, 5173)

function Get-ListeningProcessIds {
    param([int]$Port)

    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    } catch {
        Write-Warning "Could not inspect port ${Port}. Try running PowerShell with sufficient permissions."
        return @()
    }

    if (-not $connections) {
        return @()
    }

    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Wait-ForPortClosed {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 15
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        if ((Get-ListeningProcessIds -Port $Port).Count -eq 0) {
            Write-Host "Port $Port is closed." -ForegroundColor Green
            return $true
        }

        Start-Sleep -Milliseconds 500
    }

    Write-Warning "Port $Port is still listening after $TimeoutSeconds seconds."
    return $false
}

function Stop-ListeningPort {
    param([int]$Port)

    $processIds = Get-ListeningProcessIds -Port $Port

    if ($processIds.Count -eq 0) {
        Write-Host "No listening process found on port $Port." -ForegroundColor DarkGray
        return
    }

    foreach ($processId in $processIds) {
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            Write-Host "Stopping process on port ${Port}: $($process.ProcessName) (PID $processId)" -ForegroundColor Yellow
            Stop-Process -Id $processId -Force
        } catch {
            Write-Host "Could not stop process with PID $processId on port ${Port}." -ForegroundColor Red
        }
    }

    Wait-ForPortClosed -Port $Port | Out-Null
}

foreach ($port in $portsToStop) {
    Stop-ListeningPort -Port $port
}
