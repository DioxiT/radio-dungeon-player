#!/usr/bin/env bash
# radio_dungeon player - установка (macOS / Linux)
# Запуск: bash setup.sh
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
OS="$(uname -s)"

echo "== radio_dungeon player: установка =="

# --- python -----------------------------------------------------------------
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then PYTHON="$cmd"; break; fi
done
if [ -z "$PYTHON" ]; then
  echo "Python не найден."
  if [ "$OS" = "Darwin" ]; then
    echo "  brew install python@3.12"
  else
    echo "  sudo apt install python3 python3-venv   (Debian/Ubuntu)"
    echo "  sudo dnf install python3                (Fedora)"
    echo "  sudo pacman -S python                   (Arch)"
  fi
  exit 1
fi
echo "Найден $("$PYTHON" --version) (нужен 3.10+, если версия старше - обнови Python)."

# --- ffmpeg (желательно, не обязательно) -------------------------------------
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ""
  echo "ffmpeg не найден в PATH - часть треков может не проигрываться. Поставить можно так:"
  if [ "$OS" = "Darwin" ]; then
    echo "  brew install ffmpeg"
  else
    echo "  sudo apt install ffmpeg   (Debian/Ubuntu)"
    echo "  sudo dnf install ffmpeg   (Fedora)"
    echo "  sudo pacman -S ffmpeg     (Arch)"
  fi
  echo "(можно продолжить и без него - доставить получится в любой момент)"
  echo ""
fi

# --- venv + зависимости ---------------------------------------------------------
if [ ! -d "$VENV" ]; then
  echo "Создаю виртуальное окружение..."
  "$PYTHON" -m venv "$VENV"
fi
echo "Ставлю зависимости (может занять пару минут)..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$BACKEND/requirements.txt"

# --- .env ------------------------------------------------------------------------
ENV_FILE="$BACKEND/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "Нужны твои личные api_id и api_hash с https://my.telegram.org/apps"
  echo "(зайди под своим Telegram-аккаунтом, раздел 'API development tools', создай приложение - любое название подойдёт)."
  read -p "TG_API_ID: " API_ID
  read -p "TG_API_HASH: " API_HASH
  read -p "Канал без @ (Enter = radio_dungeon): " CHANNEL
  CHANNEL="${CHANNEL:-radio_dungeon}"
  cat > "$ENV_FILE" <<EOF
TG_API_ID=$API_ID
TG_API_HASH=$API_HASH
TG_CHANNEL=$CHANNEL
EOF
  echo "Сохранено в backend/.env"
fi

# --- первый вход в Telegram --------------------------------------------------------
SESSION_FILE="$BACKEND/data/tg_session.session"
if [ ! -f "$SESSION_FILE" ]; then
  echo ""
  echo "Первый вход в Telegram - введи номер телефона и код из приложения, когда попросят."
  (cd "$BACKEND" && "$VENV/bin/python" -m app.login)
fi

echo ""
echo "Готово! Запускаю плеер..."
exec bash "$ROOT/run.sh"
