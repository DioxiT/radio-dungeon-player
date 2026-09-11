"""Bring the catalogue up to date with the channel, without an account and without yt-dlp.

The desktop sync expands an album link into tracks by asking yt-dlp, which is slow and
needs updating forever. The web build does not need it: a bandcamp album page already
lists its tracks, so the same expansion is a single request and a json parse.

Reads the channel through its public web preview (see app/web_sync.py), so it needs no
Telegram account - which is what lets it run unattended in CI.

    TG_DATA_DIR=catalog python tools/sync_catalog.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import bandcamp, store, web_sync  # noqa: E402
from app.config import CHANNEL  # noqa: E402

REQUEST_DELAY = float(os.environ.get("BC_REQUEST_DELAY", "1.0"))
TIMEOUT = 25
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 radio-dungeon-player"
)


def expand(client: httpx.Client, link: str) -> list[bandcamp.BcTrack]:
    """Turn one bandcamp link into its tracks."""
    html = bandcamp.fetch_page(client, link)
    if html is None:
        return []
    try:
        return bandcamp.parse_page(html, link).tracks
    except (bandcamp.NotBandcamp, ValueError):
        return []


async def main() -> int:
    state = store.load_state()
    last_id = state.get("last_id", 0)

    posts = await web_sync.fetch_posts(CHANNEL, last_id)
    print(f"новых постов: {len(posts)}")
    if not posts:
        return 0

    known = store.known_urls()
    added_total = 0

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en,ru;q=0.9"}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        for i, post in enumerate(posts, 1):
            for link in post.links:
                # Only bandcamp can be expanded (and later baked) without yt-dlp; other
                # sources are left out of the web build rather than half-supported.
                if "bandcamp.com" not in link:
                    continue
                print(f"[{i}/{len(posts)}] {link}")
                tracks = expand(client, link)
                time.sleep(REQUEST_DELAY)

                new_entries = []
                for t in tracks:
                    if t.webpage_url in known:
                        continue
                    known.add(t.webpage_url)
                    new_entries.append(
                        {
                            "id": store.track_id(t.webpage_url),
                            "webpage_url": t.webpage_url,
                            "title": t.title,
                            "artist": t.artist,
                            "thumbnail": t.thumbnail,
                            "message_id": post.id,
                            "message_text": post.text,
                            "message_date": post.date,
                        }
                    )
                if new_entries:
                    added_total += len(store.add_tracks(new_entries))

    # Move the cursor only after a full pass, so an interrupted run re-reads those posts
    # next time instead of silently skipping them.
    state["last_id"] = posts[-1].id
    store.save_state(state)
    print(f"добавлено треков: {added_total}, курсор: {state['last_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
