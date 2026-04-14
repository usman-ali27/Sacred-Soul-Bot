$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    throw "Python venv not found at $pythonPath"
}

$workerTask = "SacredSoulBot-ExecutionWorker"
$watchdogTask = "SacredSoulBot-WorkerWatchdog"

$workerCmd = "`"$pythonPath`" -u `"$PSScriptRoot\execution_worker.py`""
$watchdogCmd = "`"$pythonPath`" -u `"$PSScriptRoot\worker_watchdog.py`""

schtasks /Create /TN $workerTask /SC ONLOGON /TR $workerCmd /RL HIGHEST /F | Out-Null
schtasks /Create /TN $watchdogTask /SC ONLOGON /TR $watchdogCmd /RL HIGHEST /F | Out-Null

Write-Host "Scheduled tasks installed:"
Write-Host "- $workerTask"
Write-Host "- $watchdogTask"
