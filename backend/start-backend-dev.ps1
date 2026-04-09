param(
    [string]$BackendDir,
    [string]$PythonExe,
    [int]$Port = 8000,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

Set-Location $BackendDir

$script:backendProcess = $null
$script:lastSignature = ""

function Get-BackendSignature {
    $items = Get-ChildItem -Path $BackendDir -Recurse -File -Include *.py,*.env |
        Sort-Object FullName

    return ($items | ForEach-Object {
        "{0}|{1}|{2}" -f $_.FullName, $_.LastWriteTimeUtc.Ticks, $_.Length
    }) -join "`n"
}

function Start-BackendProcess {
    $script:backendProcess = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $BackendDir `
        -PassThru

    Write-Host "FastAPI backend started on port $Port (PID $($script:backendProcess.Id))." -ForegroundColor Green
}

function Stop-BackendProcess {
    if ($null -eq $script:backendProcess) {
        return
    }

    try {
        if (-not $script:backendProcess.HasExited) {
            Stop-Process -Id $script:backendProcess.Id -Force -ErrorAction SilentlyContinue
            $script:backendProcess.WaitForExit()
        }
    } catch {
        return
    }
}

if ($NoReload) {
    & $PythonExe -m uvicorn app:app --host 127.0.0.1 --port $Port
    exit $LASTEXITCODE
}

Write-Host "Running backend in safe dev reload mode for Windows." -ForegroundColor Cyan
Write-Host "Code changes in backend/*.py or backend/.env will restart the server automatically." -ForegroundColor DarkCyan

$script:lastSignature = Get-BackendSignature
Start-BackendProcess

try {
    while ($true) {
        Start-Sleep -Milliseconds 1200

        if ($null -ne $script:backendProcess -and $script:backendProcess.HasExited) {
            Write-Warning "Backend process exited unexpectedly. Restarting..."
            Start-Sleep -Seconds 1
            Start-BackendProcess
            $script:lastSignature = Get-BackendSignature
            continue
        }

        $currentSignature = Get-BackendSignature
        if ($currentSignature -ne $script:lastSignature) {
            Write-Host "Detected backend file change. Restarting FastAPI..." -ForegroundColor Yellow
            $script:lastSignature = $currentSignature
            Stop-BackendProcess
            Start-Sleep -Milliseconds 500
            Start-BackendProcess
        }
    }
} finally {
    Stop-BackendProcess
}
