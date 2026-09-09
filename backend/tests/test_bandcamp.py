"""Parser checks for the bandcamp page reader used by the web build.

Runs against a fixture copy of real album markup, so it needs no network.

    cd backend && .venv/bin/python tests/test_bandcamp.py
"""

import html as htmlmod
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import bandcamp  # noqa: E402

ALBUM_URL = "https://kitezhrecords.bandcamp.com/album/i"
TS = int(time.time()) + bandcamp.STREAM_TTL_SECONDS


def stream(track_id: str) -> str:
    return (
        f"https://t4.bcbits.com/stream/{track_id}/mp3-128/{track_id}"
        f"?p=0&ts={TS}&t=abc123&token={TS}_def456"
    )


TRALBUM = {
    "url": ALBUM_URL,
    "artist": "ИндрК",
    "current": {"title": "Хроники Тираноса. Часть I"},
    "trackinfo": [
        {
            "track_num": 1,
            "title": "Безжалостные Ветры Заракхары",
            "title_link": "/track/--26",
            "duration": 768.525,
            "streaming": 1,
            "file": {"mp3-128": stream("aaa111")},
        },
        {
            "track_num": 2,
            "title": "Гость с компиляции",
            "title_link": "/track/--27",
            "artist": "Другой Артист",
            "duration": 222.5,
            "streaming": 1,
            "file": {"mp3-128": stream("bbb222")},
        },
        # preorder-only: no playable file, must be dropped
        {
            "track_num": 3,
            "title": "Ещё не вышел",
            "title_link": "/track/--28",
            "streaming": 0,
            "file": None,
        },
        # streaming flag set but bandcamp gave no mp3 - also nothing to play
        {
            "track_num": 4,
            "title": "Без файла",
            "title_link": "/track/--29",
            "streaming": 1,
            "file": {},
        },
    ],
}

PAGE = (
    '<!DOCTYPE html><html><head><meta charset="utf-8">'
    '<meta property="og:image" content="https://f4.bcbits.com/img/a0213056922_5.jpg">'
    "</head><body>"
    '<div id="pgBd" data-tralbum="' + htmlmod.escape(json.dumps(TRALBUM), quote=True) + '">'
    '<a href="/album/i">альбом</a>'
    "</div></body></html>"
)

failures = []


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -> ' + detail}")
    if not condition:
        failures.append(label)


# --- album parsing ---------------------------------------------------------------
album = bandcamp.parse_page(PAGE, ALBUM_URL)

check("album url", album.url == ALBUM_URL, album.url)
check("album title", album.title == "Хроники Тираноса. Часть I", album.title)
check("album artist", album.artist == "ИндрК", album.artist)
check("artwork from og:image", album.thumbnail.endswith("a0213056922_5.jpg"), str(album.thumbnail))
check("unplayable tracks dropped", len(album.tracks) == 2, str(len(album.tracks)))

t = album.tracks[0]
check("track title", t.title == "Безжалостные Ветры Заракхары", t.title)
check("track page url is absolute", t.webpage_url == ALBUM_URL.replace("/album/i", "/track/--26"),
      t.webpage_url)
check("stream url taken from mp3-128", "/mp3-128/" in t.stream_url, t.stream_url)
check("duration kept", t.duration == 768.525, str(t.duration))
check("artwork inherited by track", t.thumbnail == album.thumbnail, str(t.thumbnail))
check("album url recorded on track", t.album_url == ALBUM_URL, str(t.album_url))
check("artist inherited from album", t.artist == "ИндрК", t.artist)
check("per-track artist wins on compilations", album.tracks[1].artist == "Другой Артист",
      album.tracks[1].artist)

# --- expiry ----------------------------------------------------------------------
exp = bandcamp.stream_expiry(t.stream_url)
check("expiry read from ts", exp == TS, str(exp))
check("expiry is ~24h out", 23 * 3600 < exp - time.time() <= 24 * 3600, str(exp - time.time()))
check("expiry of a url without ts is None", bandcamp.stream_expiry("https://x/y") is None)

# --- album url discovery from a track page ---------------------------------------
found = bandcamp.album_url_from_track_page(PAGE, ALBUM_URL.replace("/album/i", "/track/--26"))
check("album url found from track page", found == ALBUM_URL, str(found))
check("no tralbum means no album url",
      bandcamp.album_url_from_track_page("<html></html>", "https://x/track/y") is None)

# --- non-bandcamp input ----------------------------------------------------------
try:
    bandcamp.parse_page("<html><body>ничего</body></html>", "https://youtube.com/watch?v=1")
    check("page without tralbum raises", False, "no exception")
except bandcamp.NotBandcamp:
    check("page without tralbum raises", True)

print("\nFailures:", len(failures) or "none")
raise SystemExit(1 if failures else 0)
