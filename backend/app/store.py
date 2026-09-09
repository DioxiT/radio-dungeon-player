import hashlib
import json
import threading
import uuid

from .config import CHANNEL, STATE_FILE, TRACKS_FILE, USER_DATA_FILE

_lock = threading.Lock()

_DEFAULT_USER_DATA = {"post_likes": {}, "categories": {}, "track_categories": {}}


def track_id(webpage_url: str) -> str:
    return hashlib.sha1(webpage_url.encode("utf-8")).hexdigest()[:12]


def _read_json(path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_tracks() -> list[dict]:
    return _read_json(TRACKS_FILE, [])


def get_track(tid: str) -> dict | None:
    for t in load_tracks():
        if t["id"] == tid:
            return t
    return None


def known_urls() -> set[str]:
    return {t["webpage_url"] for t in load_tracks()}


def update_track(tid: str, **fields) -> bool:
    with _lock:
        tracks = load_tracks()
        for t in tracks:
            if t["id"] == tid:
                t.update(fields)
                _write_json(TRACKS_FILE, tracks)
                return True
        return False


def add_tracks(new_tracks: list[dict]) -> list[dict]:
    with _lock:
        tracks = load_tracks()
        existing = {t["webpage_url"] for t in tracks}
        added = []
        for t in new_tracks:
            if t["webpage_url"] in existing:
                continue
            existing.add(t["webpage_url"])
            tracks.append(t)
            added.append(t)
        _write_json(TRACKS_FILE, tracks)
        return added


def load_state() -> dict:
    return _read_json(STATE_FILE, {"last_id": 0})


def save_state(state: dict) -> None:
    with _lock:
        _write_json(STATE_FILE, state)


def list_posts() -> list[dict]:
    """Group tracks by the Telegram post (message_id) they came from. Tracks synced
    before message_id was tracked become their own single-track pseudo-post."""
    tracks = load_tracks()
    user_data = load_user_data()
    post_likes = user_data["post_likes"]
    track_categories = user_data["track_categories"]

    posts: dict[str, dict] = {}
    order: list[str] = []
    for t in tracks:
        mid = t.get("message_id")
        key = f"m:{mid}" if mid is not None else f"t:{t['id']}"
        if key not in posts:
            posts[key] = {
                "message_id": mid,
                "message_date": t.get("message_date"),
                "message_text": t.get("message_text", "") if mid is not None else "",
                "liked": bool(post_likes.get(str(mid))) if mid is not None else False,
                "telegram_url": f"https://t.me/{CHANNEL}/{mid}" if mid is not None else None,
                "tracks": [],
            }
            order.append(key)
        posts[key]["tracks"].append(
            {
                "id": t["id"],
                "title": t["title"],
                "artist": t.get("artist", ""),
                "thumbnail": t.get("thumbnail"),
                "webpage_url": t["webpage_url"],
                "categories": list(track_categories.get(t["id"], [])),
            }
        )
    return [posts[k] for k in order]


def track_ids_for_message(message_id: int) -> list[str]:
    return [t["id"] for t in load_tracks() if t.get("message_id") == message_id]


# --- user personalization (likes, categories) --------------------------------------
# Kept in a file sync never writes to, so re-fetching tracks can never wipe out likes
# or category assignments.


def load_user_data() -> dict:
    data = _read_json(USER_DATA_FILE, None)
    if data is None:
        return {k: dict(v) for k, v in _DEFAULT_USER_DATA.items()}
    for key, default in _DEFAULT_USER_DATA.items():
        data.setdefault(key, dict(default))
    return data


def _save_user_data(data: dict) -> None:
    # Keep one previous version around as a cheap safety net against a bad write.
    if USER_DATA_FILE.exists():
        backup = USER_DATA_FILE.with_name(USER_DATA_FILE.name + ".bak")
        backup.write_bytes(USER_DATA_FILE.read_bytes())
    _write_json(USER_DATA_FILE, data)


def migrate_liked_tracks_to_user_data() -> None:
    """One-off migration: older versions stored `liked` per-track in tracks.json. Likes
    are now per-post and live here instead, so this only needs to run once."""
    if USER_DATA_FILE.exists():
        return
    liked_message_ids = {
        str(t["message_id"]) for t in load_tracks() if t.get("liked") and t.get("message_id")
    }
    if not liked_message_ids:
        return
    with _lock:
        data = load_user_data()
        for mid in liked_message_ids:
            data["post_likes"][mid] = True
        _save_user_data(data)


def list_categories() -> list[dict]:
    data = load_user_data()
    return [{"id": cid, "name": name} for cid, name in data["categories"].items()]


def create_category(name: str) -> dict:
    with _lock:
        data = load_user_data()
        cid = uuid.uuid4().hex[:8]
        data["categories"][cid] = name
        _save_user_data(data)
        return {"id": cid, "name": name}


def delete_category(cid: str) -> bool:
    with _lock:
        data = load_user_data()
        if cid not in data["categories"]:
            return False
        del data["categories"][cid]
        for tid in list(data["track_categories"].keys()):
            cats = data["track_categories"][tid]
            if cid in cats:
                cats.remove(cid)
                if not cats:
                    del data["track_categories"][tid]
        _save_user_data(data)
        return True


def is_post_liked(message_id: int) -> bool:
    data = load_user_data()
    return bool(data["post_likes"].get(str(message_id)))


def set_post_liked(message_id: int, liked: bool) -> None:
    with _lock:
        data = load_user_data()
        if liked:
            data["post_likes"][str(message_id)] = True
        else:
            data["post_likes"].pop(str(message_id), None)
        _save_user_data(data)


def add_category_to_tracks(track_ids: list[str], category_id: str) -> bool:
    with _lock:
        data = load_user_data()
        if category_id not in data["categories"]:
            return False
        for tid in track_ids:
            cats = data["track_categories"].setdefault(tid, [])
            if category_id not in cats:
                cats.append(category_id)
        _save_user_data(data)
        return True


def remove_category_from_tracks(track_ids: list[str], category_id: str) -> None:
    with _lock:
        data = load_user_data()
        changed = False
        for tid in track_ids:
            cats = data["track_categories"].get(tid)
            if cats and category_id in cats:
                cats.remove(category_id)
                changed = True
                if not cats:
                    del data["track_categories"][tid]
        if changed:
            _save_user_data(data)
