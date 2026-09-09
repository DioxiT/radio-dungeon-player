import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _clean(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


_api_id = _clean("TG_API_ID")
API_ID = int(_api_id) if _api_id and _api_id.isdigit() else None
API_HASH = _clean("TG_API_HASH")
CHANNEL = _clean("TG_CHANNEL") or "radio_dungeon"

# "anonymous" - read the public web preview of the channel, no Telegram account needed.
# "account"   - log in with a real account (Telethon): likes are sent to the channel.
# "auto"      - account if credentials and a saved session exist, anonymous otherwise.
TG_MODE = (_clean("TG_MODE") or "auto").lower()

# Overridable so the anonymous sync can be pointed at a local fixture server in tests.
WEB_BASE_URL = (_clean("TG_WEB_BASE_URL") or "https://t.me").rstrip("/")

# Overridable so tests never point at a real installation's session and likes.
DATA_DIR = Path(_clean("TG_DATA_DIR") or (BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SESSION_PATH = str(DATA_DIR / "tg_session")
SESSION_FILE = DATA_DIR / "tg_session.session"
TRACKS_FILE = DATA_DIR / "tracks.json"
STATE_FILE = DATA_DIR / "state.json"
USER_DATA_FILE = DATA_DIR / "user_data.json"

FRONTEND_DIR = BASE_DIR.parent / "frontend"


def has_credentials() -> bool:
    return bool(API_ID and API_HASH)


def resolve_mode() -> str:
    """Decide how to read the channel. Never raises - main.py reports problems with an
    explicit `account` request, so a missing .env degrades to anonymous instead of a
    stack trace on startup."""
    if TG_MODE == "anonymous":
        return "anonymous"
    if TG_MODE == "account":
        return "account"
    return "account" if has_credentials() and SESSION_FILE.exists() else "anonymous"
