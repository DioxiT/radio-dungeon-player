# radio_dungeon player - запуск (после setup.ps1)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "It looks like the installation hasn't been completed yet. First, run setup.ps1." -ForegroundColor Red
    exit 1
}

Start-Job -ScriptBlock { Start-Sleep -Seconds 2; Start-Process "http://localhost:8000" } | Out-Null

Write-Host "The player can be accessed at http://localhost:8000 (it will now open in your browser)." -ForegroundColor Cyan
Write-Host "Stop the server by pressing Ctrl+C." -ForegroundColor DarkGray
& $venvPython -m uvicorn app.main:app --app-dir $backend
