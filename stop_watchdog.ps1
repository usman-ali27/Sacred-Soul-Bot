$ErrorActionPreference = "Stop"

$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and $_.CommandLine -match "worker_watchdog.py"
}

if (-not $procs) {
    Write-Host "No worker_watchdog.py process found."
    exit 0
}

foreach ($p in $procs) {
    try {
        Stop-Process -Id $p.ProcessId -Force
        Write-Host "Stopped watchdog PID $($p.ProcessId)"
    }
    catch {
        Write-Warning "Failed to stop PID $($p.ProcessId): $($_.Exception.Message)"
    }
}
