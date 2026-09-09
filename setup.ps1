# radio_dungeon player - установка (Windows)
# Запуск:  powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$venv = Join-Path $backend ".venv"

Write-Host "== radio_dungeon player: installation ==" -ForegroundColor Cyan

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
    Write-Host "Python was not found (or is this a Microsoft Store placeholder?)." -ForegroundColor Red
    Write-Host "Install Python 3.10+ from https://python.org/downloads (check the “Add to PATH” box during installation) or using the following command:"
    Write-Host "  winget install Python.Python.3.12"
    Write-Host "After installation, open a new terminal and run this script again."
    exit 1
}
Write-Host "$pyVersion was found (version 3.10 or later is required; if your version is older, please reinstall Python)."

# --- ffmpeg (желательно, не обязательно) -----------------------------------
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "ffmpeg was not found in the PATH—some tracks may not play. You can set it up this way:" -ForegroundColor Yellow
    Write-Host "  winget install Gyan.FFmpeg"
    Write-Host "(after installation, open a new terminal and run this script again; or just keep going—we can deliver it later)"
    Write-Host ""
}

# --- venv + зависимости ------------------------------------------------------
if (-not (Test-Path $venv)) {
    Write-Host "I'm creating a virtual environment..."
    & $python -m venv $venv
}
$venvPython = Join-Path $venv "Scripts\python.exe"
Write-Host "I'm setting up the dependencies (this might take a couple of minutes)..."
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r (Join-Path $backend "requirements.txt")

# --- режим и .env --------------------------------------------------------------
$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "How should the player read the channel?" -ForegroundColor Cyan
    Write-Host "  1) Without logging in - the player reads the channel's public page."
    Write-Host "     Nothing to set up. Likes are kept on this computer only."
    Write-Host "  2) With a Telegram login - likes are also sent to the channel as a reaction."
    Write-Host "     Needs api_id/api_hash and a login with your phone number."
    $modeChoice = Read-Host "Choice [1]"
    if ([string]::IsNullOrWhiteSpace($modeChoice)) { $modeChoice = "1" }
    $channel = Read-Host "Channel without @ (Enter = radio_dungeon)"
    if ([string]::IsNullOrWhiteSpace($channel)) { $channel = "radio_dungeon" }

    if ($modeChoice -eq "2") {
        Write-Host ""
        Write-Host "We need your personal api_id and api_hash from https://my.telegram.org/apps" -ForegroundColor Cyan
        Write-Host "(Log in with your Telegram account, go to the “API development tools” section, and create an app—any name will do)"
        $apiId = Read-Host "TG_API_ID"
        $apiHash = Read-Host "TG_API_HASH"
        @"
TG_MODE=account
TG_CHANNEL=$channel
TG_API_ID=$apiId
TG_API_HASH=$apiHash
"@ | Set-Content -Encoding utf8 $envFile
    } else {
        @"
TG_MODE=anonymous
TG_CHANNEL=$channel
"@ | Set-Content -Encoding utf8 $envFile
    }
    Write-Host "Saved in backend\.env"
}

# --- первый вход в Telegram (только для режима с авторизацией) ------------------
$sessionFile = Join-Path $backend "data\tg_session.session"
if ((Select-String -Path $envFile -Pattern '^TG_MODE=account' -Quiet) -and (-not (Test-Path $sessionFile))) {
    Write-Host ""
    Write-Host "When you log in to Telegram for the first time, enter your phone number and the code from the app when prompted." -ForegroundColor Cyan
    Push-Location $backend
    & $venvPython -m app.login
    Pop-Location
}

Write-Host ""
Write-Host "All done! I'm starting the player..." -ForegroundColor Green
& (Join-Path $root "run.ps1")
