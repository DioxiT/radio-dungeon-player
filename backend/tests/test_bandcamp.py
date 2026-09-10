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

# --- rate limits ------------------------------------------------------------------
# Refreshing the catalogue is hundreds of requests in a row and bandcamp answers 429
# once it has had enough, so giving up on the first one loses those albums from the site.

check("Retry-After в секундах уважается", bandcamp.retry_delay(0, "7") == 7,
      str(bandcamp.retry_delay(0, "7")))
check("Retry-After ограничен потолком",
      bandcamp.retry_delay(0, "99999") == bandcamp.MAX_BACKOFF,
      str(bandcamp.retry_delay(0, "99999")))
check("Retry-After датой не ломает расчёт",
      bandcamp.retry_delay(0, "Wed, 21 Oct 2026 07:28:00 GMT") == bandcamp.BACKOFF_BASE,
      str(bandcamp.retry_delay(0, "Wed, 21 Oct 2026 07:28:00 GMT")))
check("без Retry-After пауза растёт",
      bandcamp.retry_delay(0, None) < bandcamp.retry_delay(1, None) < bandcamp.retry_delay(2, None))
check("пауза не превышает потолок", bandcamp.retry_delay(50, None) == bandcamp.MAX_BACKOFF)


class _Reply:
    def __init__(self, status, text="", headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}


class _FakeClient:
    """Stands in for httpx.Client, handing out a scripted sequence of replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def get(self, url):
        self.calls += 1
        return self.replies.pop(0) if self.replies else _Reply(200, "последний")


# Keep the test instant: the point is the decision to retry, not the waiting.
_real_base, _real_max = bandcamp.BACKOFF_BASE, bandcamp.MAX_BACKOFF
bandcamp.BACKOFF_BASE, bandcamp.MAX_BACKOFF = 0, 0

quiet = lambda *a, **k: None  # noqa: E731

c = _FakeClient([_Reply(429, headers={"Retry-After": "0"}), _Reply(429), _Reply(200, "готово")])
check("429 пережидается и запрос повторяется",
      bandcamp.fetch_page(c, "https://x/a", log=quiet) == "готово", "не дождался")
check("повторов ровно столько, сколько нужно", c.calls == 3, str(c.calls))

c = _FakeClient([_Reply(503), _Reply(200, "ок")])
check("5xx тоже повторяется", bandcamp.fetch_page(c, "https://x/b", log=quiet) == "ок")

c = _FakeClient([_Reply(404, "нет такого")])
check("404 не повторяется", bandcamp.fetch_page(c, "https://x/c", log=quiet) is None)
check("на 404 ровно один запрос", c.calls == 1, str(c.calls))

c = _FakeClient([_Reply(429) for _ in range(bandcamp.MAX_ATTEMPTS + 2)])
check("бесконечный 429 заканчивается сдачей",
      bandcamp.fetch_page(c, "https://x/d", log=quiet) is None)
check("попыток не больше лимита", c.calls == bandcamp.MAX_ATTEMPTS, str(c.calls))


class _BoomClient:
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def get(self, url):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise OSError("сеть отвалилась")
        return _Reply(200, "восстановилось")


c = _BoomClient(2)
check("сетевая ошибка тоже повторяется",
      bandcamp.fetch_page(c, "https://x/e", log=quiet) == "восстановилось")

bandcamp.BACKOFF_BASE, bandcamp.MAX_BACKOFF = _real_base, _real_max

print("\nFailures:", len(failures) or "none")
raise SystemExit(1 if failures else 0)
