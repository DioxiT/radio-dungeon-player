#!/usr/bin/env bash
# radio_dungeon player - запуск (после setup.sh)
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
VENV_PY="$BACKEND/.venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "It looks like the installation hasn't been completed yet. First, run setup.sh."
  exit 1
fi

(
  sleep 2
  if command -v open >/dev/null 2>&1; then
    open "http://localhost:8000" 2>/dev/null || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:8000" 2>/dev/null || true
  fi
) &

echo "The player can be accessed at http://localhost:8000 (it will now open in your browser)."
echo "Stop the server by pressing Ctrl+C."
"$VENV_PY" -m uvicorn app.main:app --app-dir "$BACKEND"
