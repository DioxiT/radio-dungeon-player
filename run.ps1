# radio_dungeon player - запуск (после setup.ps1)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Похоже, установка ещё не выполнена. Сначала запусти setup.ps1." -ForegroundColor Red
    exit 1
}

Start-Job -ScriptBlock { Start-Sleep -Seconds 2; Start-Process "http://localhost:8000" } | Out-Null

Write-Host "Плеер запускается на http://localhost:8000 (сейчас откроется в браузере)." -ForegroundColor Cyan
Write-Host "Останови сервер сочетанием Ctrl+C." -ForegroundColor DarkGray
& $venvPython -m uvicorn app.main:app --app-dir $backend
