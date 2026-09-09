"""End-to-end check of anonymous mode: startup without credentials, sync through the
web preview, likes kept local, and a loud failure when TG_MODE=account has no keys.

Only yt-dlp is stubbed out (no network in CI); everything else runs for real.
Runs entirely in a temporary data directory and never reads or writes a real
installation's .env, Telegram session, tracks or likes - safe on a live install.

    cd backend && .venv/bin/python tests/test_anonymous_mode.py
"""

import importlib
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
DATA = Path(tempfile.mkdtemp(prefix="rdp-test-"))
CHANNEL = "radio_dungeon"
TOTAL = 25

MSG = """
<div class="tgme_widget_message js-widget_message" data-post="{ch}/{mid}">
<div class="tgme_widget_message_bubble">
<div class="tgme_widget_message_text js-message_text" dir="auto">ПОСТ {mid} <a href="https://band{mid}.bandcamp.com/album/x">СЛУШАЕМ</a></div>
<div class="tgme_widget_message_footer">
<a class="tgme_widget_message_date" href="https://t.me/{ch}/{mid}"><time datetime="2026-08-01T07:0{d}:19+00:00"></time></a>
</div></div></div>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        before = parse_qs(urlparse(self.path).query).get("before", [None])[0]
        top = int(before) - 1 if before else TOTAL
        body = "".join(
            MSG.format(ch=CHANNEL, mid=i, d=i % 10) for i in range(max(1, top - 19), top + 1)
        )
        payload = f"<html><body>{body}</body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

# python-dotenv never overrides variables that are already set, so pinning these
# here neutralizes a real backend/.env without touching the file: the test always
# runs anonymously, against the fixture server, in a throwaway data directory.
os.environ["TG_MODE"] = "anonymous"
os.environ["TG_CHANNEL"] = CHANNEL
os.environ["TG_API_ID"] = ""
os.environ["TG_API_HASH"] = ""
os.environ["TG_DATA_DIR"] = str(DATA)
os.environ["TG_WEB_BASE_URL"] = f"http://127.0.0.1:{server.server_address[1]}"

failures = []


def check(label, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {label}{'' if cond else '  -> ' + detail}")
    if not cond:
        failures.append(label)


def wait_for_sync(sync_core, limit=15.0):
    deadline = time.time() + limit
    while time.time() < deadline:
        if not sync_core.get_status()["running"]:
            return
        time.sleep(0.05)


try:
    from fastapi.testclient import TestClient

    from app import config, main, resolver, store, sync_core, web_sync

    # --- mode resolution -------------------------------------------------------
    check("runs in a temp data dir", str(config.DATA_DIR) == str(DATA), str(config.DATA_DIR))
    check("no credentials means anonymous", main.MODE == "anonymous", main.MODE)
    check("no Telethon client built", main.client is None)
    check("default channel", config.CHANNEL == "radio_dungeon", config.CHANNEL)

    web_sync.PAGE_DELAY = 0

    # Stand in for yt-dlp: one album link resolves to two tracks.
    resolver.probe = lambda url: [
        {
            "webpage_url": f"{url.rstrip('/')}/t{n}",
            "title": f"Track {n}",
            "artist": "Band",
            "thumbnail": None,
        }
        for n in (1, 2)
    ]

    with TestClient(main.app) as c:
        wait_for_sync(sync_core)

        # --- sync ---------------------------------------------------------------
        status = sync_core.get_status()
        check("sync finished without error", status["error"] is None, str(status["error"]))
        check("every post processed", status["processed"] == TOTAL, str(status))
        check("two tracks added per post", status["added"] == TOTAL * 2, str(status))
        check("cursor saved", store.load_state()["last_id"] == TOTAL, str(store.load_state()))

        posts = c.get("/api/posts").json()
        check("posts exposed", len(posts) == TOTAL, str(len(posts)))
        check("tracks grouped per post", all(len(p["tracks"]) == 2 for p in posts))
        newest = [p for p in posts if p["message_id"] == TOTAL][0]
        check("post text stored", newest["message_text"] == f"ПОСТ {TOTAL} СЛУШАЕМ",
              repr(newest["message_text"]))
        check("post date stored", newest["message_date"] == "2026-08-01T07:05:19+00:00",
              str(newest["message_date"]))
        check("telegram url built", newest["telegram_url"] == f"https://t.me/{CHANNEL}/{TOTAL}",
              str(newest["telegram_url"]))

        # --- mode endpoint ------------------------------------------------------
        mode = c.get("/api/mode").json()
        check("/api/mode reports anonymous", mode["mode"] == "anonymous", str(mode))
        check("likes_reach_telegram is false", mode["likes_reach_telegram"] is False, str(mode))

        # --- likes --------------------------------------------------------------
        r = c.post(f"/api/posts/{TOTAL}/like")
        check("like succeeds without an account", r.status_code == 200, r.text)
        check("like applied", r.json()["liked"] is True, r.text)
        check("like flagged as local", r.json()["synced_to_telegram"] is False, r.text)
        check("like persisted", store.is_post_liked(TOTAL))
        check("unknown post still 404s", c.post("/api/posts/99999/like").status_code == 404)

        # --- resync is a no-op and preserves user data --------------------------
        before_count = len(store.load_tracks())
        c.post("/api/sync")
        wait_for_sync(sync_core)
        check("resync adds no duplicates", len(store.load_tracks()) == before_count,
              str(len(store.load_tracks())))
        check("like survived the resync", store.is_post_liked(TOTAL))

        r = c.post(f"/api/posts/{TOTAL}/like")
        check("second click removes the like", r.json()["liked"] is False, r.text)

    # --- account mode without credentials must fail loudly ----------------------
    os.environ["TG_MODE"] = "account"
    for mod in ("app.main", "app.config"):
        sys.modules.pop(mod, None)
    try:
        importlib.import_module("app.main")
        check("TG_MODE=account without keys raises", False, "import succeeded")
    except RuntimeError as exc:
        check("TG_MODE=account without keys raises", "TG_API_ID" in str(exc), str(exc))
finally:
    server.shutdown()
    shutil.rmtree(DATA, ignore_errors=True)

print("\nFailures:", len(failures) or "none")
raise SystemExit(1 if failures else 0)
