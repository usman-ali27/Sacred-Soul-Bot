$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Python venv not found at .venv\Scripts\python.exe"
}

$cmd = ".venv\Scripts\python.exe -u worker_watchdog.py"
Write-Host "Starting ICT worker watchdog..."
Write-Host "Command: $cmd"

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoLogo",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", "Set-Location '$PSScriptRoot'; $cmd"
) -WorkingDirectory $PSScriptRoot | Out-Null

Write-Host "Watchdog process launched in a new PowerShell window."
