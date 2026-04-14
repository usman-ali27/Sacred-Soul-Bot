$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Python venv not found at .venv\Scripts\python.exe"
}

$cmd = ".venv\Scripts\python.exe -u execution_worker.py"
Write-Host "Starting ICT execution worker..."
Write-Host "Command: $cmd"

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoLogo",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", "Set-Location '$PSScriptRoot'; $cmd"
) -WorkingDirectory $PSScriptRoot | Out-Null

Write-Host "Worker process launched in a new PowerShell window."
