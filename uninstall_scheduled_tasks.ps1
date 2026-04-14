$ErrorActionPreference = "Stop"

$tasks = @("SacredSoulBot-ExecutionWorker", "SacredSoulBot-WorkerWatchdog")

foreach ($task in $tasks) {
    schtasks /Delete /TN $task /F 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Removed task: $task"
    }
    else {
        Write-Host "Task not found (or already removed): $task"
    }
}
