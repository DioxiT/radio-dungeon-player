#!/usr/bin/env bash
# radio_dungeon player - установка (macOS / Linux)
# Запуск: bash setup.sh
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
OS="$(uname -s)"

echo "== radio_dungeon player: installation =="

# --- python -----------------------------------------------------------------
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then PYTHON="$cmd"; break; fi
done
if [ -z "$PYTHON" ]; then
  echo "Python not found."
  if [ "$OS" = "Darwin" ]; then
    echo "  brew install python@3.12"
  else
    echo "  sudo apt install python3 python3-venv   (Debian/Ubuntu)"
    echo "  sudo dnf install python3                (Fedora)"
    echo "  sudo pacman -S python                   (Arch)"
  fi
  exit 1
fi
echo "Found $(“$PYTHON” --version) (version 3.10 or later is required; if your version is older, please update Python)."

# --- ffmpeg (желательно, не обязательно) -------------------------------------
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ""
  echo "ffmpeg was not found in the PATH—some tracks may not play. You can set it up this way:"
  if [ "$OS" = "Darwin" ]; then
    echo "  brew install ffmpeg"
  else
    echo "  sudo apt install ffmpeg   (Debian/Ubuntu)"
    echo "  sudo dnf install ffmpeg   (Fedora)"
    echo "  sudo pacman -S ffmpeg     (Arch)"
  fi
  echo "(You can continue without it—you'll be able to deliver it at any time.)"
  echo ""
fi

# --- venv + зависимости ---------------------------------------------------------
if [ ! -d "$VENV" ]; then
  echo "I'm creating a virtual environment..."
  "$PYTHON" -m venv "$VENV"
fi
echo "I'm setting up the dependencies (this might take a couple of minutes)..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$BACKEND/requirements.txt"

# --- .env ------------------------------------------------------------------------
ENV_FILE="$BACKEND/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "We need your personal api_id and api_hash from https://my.telegram.org/apps"
  echo "(Log in with your Telegram account, go to the “API development tools” section, and create an app—any name will do)"
  read -p "TG_API_ID: " API_ID
  read -p "TG_API_HASH: " API_HASH
  read -p "Channel without @ (Enter = radio_dungeon): " CHANNEL
  CHANNEL="${CHANNEL:-radio_dungeon}"
  cat > "$ENV_FILE" <<EOF
TG_API_ID=$API_ID
TG_API_HASH=$API_HASH
TG_CHANNEL=$CHANNEL
EOF
  echo "Saved in backend/.env"
fi

# --- первый вход в Telegram --------------------------------------------------------
SESSION_FILE="$BACKEND/data/tg_session.session"
if [ ! -f "$SESSION_FILE" ]; then
  echo ""
  echo "When you log in to Telegram for the first time, enter your phone number and the code from the app when prompted."
  (cd "$BACKEND" && "$VENV/bin/python" -m app.login)
fi

echo ""
echo "All done! I'm starting the player..."
exec bash "$ROOT/run.sh"
