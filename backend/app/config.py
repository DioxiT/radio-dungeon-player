import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
CHANNEL = os.environ.get("TG_CHANNEL", "radio_dungeon")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SESSION_PATH = str(DATA_DIR / "tg_session")
TRACKS_FILE = DATA_DIR / "tracks.json"
STATE_FILE = DATA_DIR / "state.json"
USER_DATA_FILE = DATA_DIR / "user_data.json"

FRONTEND_DIR = BASE_DIR.parent / "frontend"
