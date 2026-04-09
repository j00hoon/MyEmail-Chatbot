param(
    [string]$SourceDir,
    [string]$RuntimeDir = "",
    [int]$Port = 5173,
    [switch]$NoWatch
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SourceDir)) {
    throw "Frontend source directory not found: $SourceDir"
}

if (-not $RuntimeDir) {
    $RuntimeDir = "C:\temp\myEmail-chatbot-frontend-dev"
}

$npmCmd = "C:\Program Files\nodejs\npm.cmd"
if (-not (Test-Path $npmCmd)) {
    throw "npm.cmd not found at $npmCmd"
}

$sourceNodeModulesDir = Join-Path $SourceDir "node_modules"
if (-not (Test-Path $sourceNodeModulesDir)) {
    throw "Frontend dependencies were not found: $sourceNodeModulesDir"
}

$script:viteProcess = $null
$script:lastSignature = ""

function Invoke-Robocopy {
    param(
        [string]$From,
        [string]$To,
        [string[]]$ExcludedDirs = @("dist", ".vite", ".runtime-dev", ".frontend-runtime-dev", "node_modules")
    )

    New-Item -ItemType Directory -Path $To -Force | Out-Null

    $arguments = @(
        "`"$From`"",
        "`"$To`"",
        "/MIR"
    )

    if ($ExcludedDirs.Count -gt 0) {
        $arguments += "/XD"
        $arguments += $ExcludedDirs
    }

    & robocopy @arguments | Out-Null
    $exitCode = $LASTEXITCODE
    if ($exitCode -gt 7) {
        throw "robocopy failed with exit code $exitCode"
    }
}

function Sync-NodeModulesRuntime {
    $runtimeNodeModulesDir = Join-Path $RuntimeDir "node_modules"

    if (Test-Path $runtimeNodeModulesDir) {
        Remove-Item -LiteralPath $runtimeNodeModulesDir -Recurse -Force
    }

    Invoke-Robocopy -From $sourceNodeModulesDir -To $runtimeNodeModulesDir -ExcludedDirs @()
}

function Test-FrontendDependenciesHealthy {
    $viteCliPath = Join-Path $RuntimeDir "node_modules\vite\dist\node\cli.js"
    return (Test-Path $viteCliPath)
}

function Get-FrontendSignature {
    $items = Get-ChildItem -Path $SourceDir -Recurse -File |
        Where-Object {
            $_.FullName -notmatch '\\dist\\' -and
            $_.FullName -notmatch '\\\.vite\\'
        } |
        Sort-Object FullName

    return ($items | ForEach-Object {
        "{0}|{1}|{2}" -f $_.FullName, $_.LastWriteTimeUtc.Ticks, $_.Length
    }) -join "`n"
}

function Sync-FrontendRuntime {
    Invoke-Robocopy -From $SourceDir -To $RuntimeDir
    if (-not (Test-FrontendDependenciesHealthy)) {
        Write-Host "Refreshing runtime node_modules from source..." -ForegroundColor Yellow
        Sync-NodeModulesRuntime

        if (-not (Test-FrontendDependenciesHealthy)) {
            throw "Frontend runtime dependencies are incomplete after refresh: $RuntimeDir"
        }
    }
}

function Start-ViteProcess {
    $script:viteProcess = Start-Process `
        -FilePath $npmCmd `
        -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$Port", "--strictPort") `
        -WorkingDirectory $RuntimeDir `
        -PassThru

    Write-Host "React frontend started on port $Port (PID $($script:viteProcess.Id))." -ForegroundColor Green
}

function Stop-ViteProcess {
    if ($null -eq $script:viteProcess) {
        return
    }

    try {
        if (-not $script:viteProcess.HasExited) {
            Stop-Process -Id $script:viteProcess.Id -Force -ErrorAction SilentlyContinue
            $script:viteProcess.WaitForExit()
        }
    } catch {
        return
    }
}

Sync-FrontendRuntime

if ($NoWatch) {
    Set-Location $RuntimeDir
    & $npmCmd run dev -- --host 127.0.0.1 --port $Port --strictPort
    exit $LASTEXITCODE
}

Write-Host "Running frontend from mirrored runtime workspace: $RuntimeDir" -ForegroundColor Cyan
Write-Host "Changes in frontend source will be mirrored automatically." -ForegroundColor DarkCyan

$script:lastSignature = Get-FrontendSignature
Start-ViteProcess

try {
    while ($true) {
        Start-Sleep -Milliseconds 1500

        if ($null -ne $script:viteProcess -and $script:viteProcess.HasExited) {
            Write-Warning "Frontend process exited unexpectedly. Resyncing and restarting..."
            Sync-FrontendRuntime
            Start-Sleep -Seconds 1
            Start-ViteProcess
            $script:lastSignature = Get-FrontendSignature
            continue
        }

        $currentSignature = Get-FrontendSignature
        if ($currentSignature -ne $script:lastSignature) {
            $script:lastSignature = $currentSignature
            Sync-FrontendRuntime
        }
    }
} finally {
    Stop-ViteProcess
}
