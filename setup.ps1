# radio_dungeon player - установка (Windows)
# Запуск:  powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$venv = Join-Path $backend ".venv"

Write-Host "== radio_dungeon player: установка ==" -ForegroundColor Cyan

# --- Python ---------------------------------------------------------------
$python = $null
foreach ($cmd in @("python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        try {
            $out = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0) { $python = $cmd; $pyVersion = $out; break }
        } catch {}
    }
}
if (-not $python) {
    Write-Host "Python не найден (или это заглушка Microsoft Store)." -ForegroundColor Red
    Write-Host "Установи Python 3.10+ с https://python.org/downloads (отметь 'Add to PATH' при установке) или командой:"
    Write-Host "  winget install Python.Python.3.12"
    Write-Host "После установки открой новый терминал и запусти этот скрипт заново."
    exit 1
}
Write-Host "Найден $pyVersion (нужен 3.10+, если версия старше - переустанови Python)."

# --- ffmpeg (желательно, не обязательно) -----------------------------------
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "ffmpeg не найден в PATH - часть треков может не проигрываться. Поставить можно так:" -ForegroundColor Yellow
    Write-Host "  winget install Gyan.FFmpeg"
    Write-Host "(после установки открой новый терминал и запусти этот скрипт заново; либо просто продолжай - можно доставить позже)"
    Write-Host ""
}

# --- venv + зависимости ------------------------------------------------------
if (-not (Test-Path $venv)) {
    Write-Host "Создаю виртуальное окружение..."
    & $python -m venv $venv
}
$venvPython = Join-Path $venv "Scripts\python.exe"
Write-Host "Ставлю зависимости (может занять пару минут)..."
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r (Join-Path $backend "requirements.txt")

# --- .env ----------------------------------------------------------------------
$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "Нужны твои личные api_id и api_hash с https://my.telegram.org/apps" -ForegroundColor Cyan
    Write-Host "(зайди под своим Telegram-аккаунтом, раздел 'API development tools', создай приложение - любое название подойдёт)."
    $apiId = Read-Host "TG_API_ID"
    $apiHash = Read-Host "TG_API_HASH"
    $channel = Read-Host "Канал без @ (Enter = radio_dungeon)"
    if ([string]::IsNullOrWhiteSpace($channel)) { $channel = "radio_dungeon" }
    @"
TG_API_ID=$apiId
TG_API_HASH=$apiHash
TG_CHANNEL=$channel
"@ | Set-Content -Encoding utf8 $envFile
    Write-Host "Сохранено в backend\.env"
}

# --- первый вход в Telegram ----------------------------------------------------
$sessionFile = Join-Path $backend "data\tg_session.session"
if (-not (Test-Path $sessionFile)) {
    Write-Host ""
    Write-Host "Первый вход в Telegram - введи номер телефона и код из приложения, когда попросят." -ForegroundColor Cyan
    Push-Location $backend
    & $venvPython -m app.login
    Pop-Location
}

Write-Host ""
Write-Host "Готово! Запускаю плеер..." -ForegroundColor Green
& (Join-Path $root "run.ps1")
