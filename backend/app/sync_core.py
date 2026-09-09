"""Source-agnostic half of the channel sync.

Both backends (a logged-in Telethon client and the anonymous web-preview scraper)
produce the same `Post` objects; everything after that - probing links with yt-dlp,
storing tracks, moving the cursor, reporting progress - lives here.
"""

import asyncio
import re
from dataclasses import dataclass, field

from . import resolver, store

URL_RE = re.compile(r"https?://\S+")

PROBE_TIMEOUT = 25  # seconds - a single unresponsive link must not stall the whole sync

# Domains that are never music sources - skip probing these to save time.
_SKIP_DOMAINS = ("t.me", "telegram.me", "twitter.com", "x.com", "instagram.com")

_status = {"running": False, "processed": 0, "total": 0, "added": 0, "error": None}


@dataclass
class Post:
    """One channel post, normalized across sync backends."""

    id: int
    text: str = ""
    date: str | None = None  # ISO 8601
    links: list[str] = field(default_factory=list)


def get_status() -> dict:
    return dict(_status)


def clean_links(links) -> list[str]:
    """Deduplicate, strip trailing punctuation and drop domains that never hold music."""
    out: list[str] = []
    seen: set[str] = set()
    for link in links:
        if not link:
            continue
        link = link.strip().rstrip(").,»\"'")
        if not link.startswith(("http://", "https://")):
            continue
        if any(d in link for d in _SKIP_DOMAINS):
            continue
        if link in seen:
            continue
        seen.add(link)
        out.append(link)
    return out


async def sync(fetch_posts) -> None:
    """Run one sync pass.

    `fetch_posts` is an async callable taking the last seen message id and returning
    the posts newer than it, oldest first.
    """
    if _status["running"]:
        return

    _status.update(running=True, processed=0, total=0, added=0, error=None)
    added_total = 0
    try:
        state = store.load_state()
        last_id = state.get("last_id", 0)
        posts = await fetch_posts(last_id)
        _status["total"] = len(posts)
        print(f"[sync] fetched {len(posts)} new post(s)")

        known = store.known_urls()
        for i, post in enumerate(posts):
            for link in post.links:
                if link in known:
                    continue
                print(f"[sync] ({i + 1}/{len(posts)}) probing {link}")
                try:
                    entries = await asyncio.wait_for(
                        asyncio.to_thread(resolver.probe, link), timeout=PROBE_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    print(f"[sync] timed out probing {link}, skipping")
                    continue
                if not entries:
                    continue
                new_entries = []
                for e in entries:
                    tid = store.track_id(e["webpage_url"])
                    if e["webpage_url"] in known:
                        # Already stored from a previous sync - backfill post info if an
                        # older run added this track before that field existed.
                        existing = store.get_track(tid)
                        if existing and not existing.get("message_id"):
                            store.update_track(
                                tid,
                                message_id=post.id,
                                message_text=post.text,
                                message_date=post.date,
                            )
                        continue
                    known.add(e["webpage_url"])
                    e["id"] = tid
                    e["message_id"] = post.id
                    e["message_text"] = post.text
                    e["message_date"] = post.date
                    new_entries.append(e)
                if new_entries:
                    # Persist as soon as a link resolves, so the player can show and
                    # play tracks while the rest of the sync is still running.
                    added_total += len(store.add_tracks(new_entries))
                    _status["added"] = added_total
            _status["processed"] = i + 1

        # Only move the cursor forward once everything above finished, so a crash or
        # an interrupted request doesn't silently skip messages on the next sync.
        if posts:
            state["last_id"] = posts[-1].id
            store.save_state(state)
        print(f"[sync] done, added {added_total} track(s)")
    except Exception as exc:
        _status["error"] = str(exc)
        print(f"[sync] failed: {exc}")
        raise
    finally:
        _status["running"] = False
