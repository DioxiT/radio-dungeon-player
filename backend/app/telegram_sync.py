import asyncio
import re

from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import MessageEntityTextUrl, ReactionEmoji

from . import resolver, store

URL_RE = re.compile(r"https?://\S+")

PROBE_TIMEOUT = 25  # seconds - a single unresponsive link must not stall the whole sync

# Domains that are never music sources - skip probing these to save time.
_SKIP_DOMAINS = ("t.me", "telegram.me", "twitter.com", "x.com", "instagram.com")

_status = {"running": False, "processed": 0, "total": 0, "added": 0, "error": None}


def get_status() -> dict:
    return dict(_status)


def extract_links(message) -> list[str]:
    links = set()
    text = message.raw_text or ""
    for m in URL_RE.findall(text):
        links.add(m.rstrip(").,»\"'"))
    if message.entities:
        for entity in message.entities:
            if isinstance(entity, MessageEntityTextUrl):
                links.add(entity.url)
    return [l for l in links if not any(d in l for d in _SKIP_DOMAINS)]


async def fetch_new_messages(client, channel: str, last_id: int) -> list:
    messages = []
    async for msg in client.iter_messages(channel, min_id=last_id, reverse=True, limit=None):
        messages.append(msg)
    return messages


async def sync(client, channel: str) -> list[dict]:
    if _status["running"]:
        return []

    _status.update(running=True, processed=0, total=0, added=0, error=None)
    added_total = 0
    try:
        state = store.load_state()
        last_id = state.get("last_id", 0)
        messages = await fetch_new_messages(client, channel, last_id)
        _status["total"] = len(messages)
        print(f"[sync] fetched {len(messages)} new message(s) from {channel}")

        known = store.known_urls()
        for i, msg in enumerate(messages):
            for link in extract_links(msg):
                if link in known:
                    continue
                print(f"[sync] ({i + 1}/{len(messages)}) probing {link}")
                try:
                    entries = await asyncio.wait_for(
                        asyncio.to_thread(resolver.probe, link), timeout=PROBE_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    print(f"[sync] timed out probing {link}, skipping")
                    continue
                if not entries:
                    continue
                message_date = msg.date.isoformat() if msg.date else None
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
                                message_id=msg.id,
                                message_text=msg.raw_text or "",
                                message_date=message_date,
                            )
                        continue
                    known.add(e["webpage_url"])
                    e["id"] = tid
                    e["message_id"] = msg.id
                    e["message_text"] = msg.raw_text or ""
                    e["message_date"] = message_date
                    new_entries.append(e)
                if new_entries:
                    # Persist as soon as a link resolves, so the player can show and
                    # play tracks while the rest of the sync is still running.
                    added_total += len(store.add_tracks(new_entries))
                    _status["added"] = added_total
            _status["processed"] = i + 1

        # Only move the cursor forward once everything above finished, so a crash or
        # an interrupted request doesn't silently skip messages on the next sync.
        if messages:
            state["last_id"] = messages[-1].id
            store.save_state(state)
        print(f"[sync] done, added {added_total} track(s)")
    except Exception as exc:
        _status["error"] = str(exc)
        print(f"[sync] failed: {exc}")
        raise
    finally:
        _status["running"] = False
    return []


async def set_like(client, channel: str, message_id: int, liked: bool) -> None:
    entity = await client.get_entity(channel)
    reaction = [ReactionEmoji(emoticon="👍")] if liked else []
    await client(
        SendReactionRequest(
            peer=entity,
            msg_id=message_id,
            reaction=reaction,
            add_to_recent=True,
        )
    )
