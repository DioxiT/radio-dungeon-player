"""Parser and pagination checks for the anonymous sync.

Runs against a local server that reproduces t.me/s/ markup, so it needs no network.

    cd backend && .venv/bin/python tests/test_web_sync.py
"""

import asyncio
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CHANNEL = "radio_dungeon"
TOTAL = 45  # posts 1..45, served 20 per page like the real preview

MESSAGE_TMPL = """
<div class="tgme_widget_message_wrap js-widget_message_wrap">
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="{channel}/{mid}" data-view="eyJj">
<div class="tgme_widget_message_user"><a href="https://t.me/{channel}"><i class="tgme_widget_message_user_photo"></i></a></div>
<div class="tgme_widget_message_bubble">
<div class="tgme_widget_message_text js-message_text" dir="auto">ПОСТ {mid} <a href="https://band{mid}.bandcamp.com/album/x" target="_blank" rel="noopener">СЛУШАЕМ ВОТ ЭТО</a> И ЕЩЁ<br/>ВТОРАЯ СТРОКА https://extra{mid}.bandcamp.com/track/y <a href="https://t.me/somechannel/5">репост</a></div>
<a class="tgme_widget_message_link_preview" href="https://band{mid}.bandcamp.com/album/x">
<div class="link_preview_title">Album {mid}</div>
<div class="tgme_widget_message_description">описание превью, тут ссылок нет</div>
</a>
<div class="tgme_widget_message_footer compact js-message_footer">
<div class="tgme_widget_message_info short js-message_info">
<span class="tgme_widget_message_views">177</span>
<a class="tgme_widget_message_date" href="https://t.me/{channel}/{mid}"><time datetime="2026-08-{day:02d}T07:06:19+00:00" class="time">07:06</time></a>
</div>
</div>
</div>
</div>
</div>
"""

PAGE_TMPL = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>ch</title></head>
<body class="tgme_body_wrap"><main class="tgme_main">{body}</main></body></html>"""

requested = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith(f"/s/{CHANNEL}"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"nope")
            return

        before = parse_qs(parsed.query).get("before", [None])[0]
        requested.append(int(before) if before else None)
        top = int(before) - 1 if before else TOTAL
        ids = range(max(1, top - 19), top + 1)

        body = "".join(
            MESSAGE_TMPL.format(channel=CHANNEL, mid=i, day=(i % 28) + 1) for i in ids
        )
        payload = PAGE_TMPL.format(body=body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

os.environ["TG_WEB_BASE_URL"] = f"http://127.0.0.1:{server.server_address[1]}"
os.environ["TG_MODE"] = "anonymous"

from app import web_sync  # noqa: E402  (import after env is set)

web_sync.PAGE_DELAY = 0

failures = []


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -> ' + detail}")
    if not condition:
        failures.append(label)


# --- full backfill ------------------------------------------------------------
posts = asyncio.run(web_sync.fetch_posts(CHANNEL, 0))

check("all posts collected", len(posts) == TOTAL, f"got {len(posts)}")
check("ascending by id", [p.id for p in posts] == list(range(1, TOTAL + 1)))
check("walked 3 pages", len(requested) == 3, f"requests={requested}")
check("cursor moves backwards", requested == [None, 26, 6], f"requests={requested}")

p = posts[-1]
check("post id", p.id == 45)
check("date from time[datetime]", p.date == "2026-08-18T07:06:19+00:00", str(p.date))
check("text extracted", p.text.startswith("ПОСТ 45 СЛУШАЕМ ВОТ ЭТО И ЕЩЁ"), repr(p.text[:60]))
check("<br> became a newline", "\nВТОРАЯ СТРОКА" in p.text, repr(p.text))
check("preview description excluded", "описание превью" not in p.text)

check("href link found", "https://band45.bandcamp.com/album/x" in p.links, str(p.links))
check("bare url found", "https://extra45.bandcamp.com/track/y" in p.links, str(p.links))
check("t.me filtered out", not any("t.me" in l for l in p.links), str(p.links))
check("no duplicates", len(p.links) == len(set(p.links)), str(p.links))
check("exactly 2 links", len(p.links) == 2, str(p.links))

# --- incremental --------------------------------------------------------------
requested.clear()
new_posts = asyncio.run(web_sync.fetch_posts(CHANNEL, 40))
check("only newer posts", [x.id for x in new_posts] == [41, 42, 43, 44, 45],
      str([x.id for x in new_posts]))
check("single page fetched", len(requested) == 1, f"requests={requested}")

requested.clear()
check("nothing new means empty", asyncio.run(web_sync.fetch_posts(CHANNEL, TOTAL)) == [])

# --- error handling -----------------------------------------------------------
try:
    asyncio.run(web_sync.fetch_posts("no_such_channel", 0))
    check("404 raises a clear error", False, "no exception raised")
except web_sync.ChannelUnavailable as exc:
    check("404 raises a clear error", "TG_CHANNEL" in str(exc), str(exc))

server.shutdown()
print("\nFailures:", len(failures) or "none")
raise SystemExit(1 if failures else 0)
