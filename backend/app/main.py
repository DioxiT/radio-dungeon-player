import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telethon import TelegramClient

from . import resolver, store, telegram_sync
from .config import API_HASH, API_ID, CHANNEL, FRONTEND_DIR, SESSION_PATH

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
_sync_task: asyncio.Task | None = None


def _launch_sync_task():
    global _sync_task
    if _sync_task and not _sync_task.done():
        return

    async def runner():
        try:
            await telegram_sync.sync(client, CHANNEL)
        except Exception:
            pass  # already recorded in telegram_sync.get_status()

    _sync_task = asyncio.create_task(runner())


@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError(
            "Telegram session is not authorized. Run `python -m app.login` once from the "
            "backend directory to log in interactively, then restart the server."
        )
    store.migrate_liked_tracks_to_user_data()
    # Posts show up rarely, so syncing once on startup is enough - no need to make the
    # user click "Обновить" every time they open the player.
    _launch_sync_task()
    yield
    await client.disconnect()


app = FastAPI(lifespan=lifespan)


class CategoryIn(BaseModel):
    name: str


@app.post("/api/sync")
async def start_sync():
    if _sync_task and not _sync_task.done():
        return {"status": "already_running", **telegram_sync.get_status()}
    _launch_sync_task()
    return {"status": "started"}


@app.get("/api/sync/status")
async def sync_status():
    return telegram_sync.get_status()


@app.get("/api/posts")
async def list_posts():
    return store.list_posts()


@app.post("/api/posts/{message_id}/like")
async def like_post(message_id: int):
    if not store.track_ids_for_message(message_id):
        raise HTTPException(404, "unknown post")
    new_liked = not store.is_post_liked(message_id)
    try:
        await telegram_sync.set_like(client, CHANNEL, message_id, new_liked)
    except Exception as exc:
        raise HTTPException(502, f"could not react: {exc}") from exc
    store.set_post_liked(message_id, new_liked)
    return {"liked": new_liked}


@app.get("/api/categories")
async def list_categories():
    return store.list_categories()


@app.post("/api/categories")
async def create_category(body: CategoryIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "category name required")
    return store.create_category(name)


@app.delete("/api/categories/{category_id}")
async def delete_category(category_id: str):
    if not store.delete_category(category_id):
        raise HTTPException(404, "unknown category")
    return {"ok": True}


@app.post("/api/tracks/{track_id}/categories/{category_id}")
async def add_track_category(track_id: str, category_id: str):
    if not store.get_track(track_id):
        raise HTTPException(404, "unknown track")
    if not store.add_category_to_tracks([track_id], category_id):
        raise HTTPException(404, "unknown category")
    return {"ok": True}


@app.delete("/api/tracks/{track_id}/categories/{category_id}")
async def remove_track_category(track_id: str, category_id: str):
    store.remove_category_from_tracks([track_id], category_id)
    return {"ok": True}


@app.post("/api/posts/{message_id}/categories/{category_id}")
async def add_post_category(message_id: int, category_id: str):
    track_ids = store.track_ids_for_message(message_id)
    if not track_ids:
        raise HTTPException(404, "unknown post")
    if not store.add_category_to_tracks(track_ids, category_id):
        raise HTTPException(404, "unknown category")
    return {"ok": True}


@app.delete("/api/posts/{message_id}/categories/{category_id}")
async def remove_post_category(message_id: int, category_id: str):
    track_ids = store.track_ids_for_message(message_id)
    store.remove_category_from_tracks(track_ids, category_id)
    return {"ok": True}


@app.get("/api/tracks/{track_id}/stream")
async def stream_track(track_id: str, request: Request):
    track = store.get_track(track_id)
    if not track:
        raise HTTPException(404, "unknown track")

    try:
        stream_url, ext = await asyncio.to_thread(resolver.resolve_stream, track["webpage_url"])
    except Exception as exc:
        raise HTTPException(502, f"could not resolve stream: {exc}") from exc

    media_type = {"mp3": "audio/mpeg", "ogg": "audio/ogg", "wav": "audio/wav", "m4a": "audio/mp4"}.get(
        ext, "audio/mpeg"
    )

    # Forward the browser's Range header upstream so seeking works: <audio> issues a
    # range request when the user scrubs the progress bar or skips with the arrow keys,
    # and without this the server always re-sent the full file from byte 0, which looks
    # like playback hanging and then resuming from the old position.
    range_header = request.headers.get("range")
    upstream_headers = {"Range": range_header} if range_header else {}

    timeout = httpx.Timeout(15.0, read=60.0)
    hc = httpx.AsyncClient(timeout=timeout)
    try:
        upstream = await hc.send(
            hc.build_request("GET", stream_url, headers=upstream_headers), stream=True
        )
    except httpx.HTTPError as exc:
        await hc.aclose()
        raise HTTPException(502, f"could not reach source: {exc}") from exc

    if upstream.status_code >= 400:
        await upstream.aclose()
        await hc.aclose()
        raise HTTPException(502, f"source returned {upstream.status_code}")

    response_headers = {"Accept-Ranges": "bytes"}
    for h in ("content-range", "content-length"):
        if h in upstream.headers:
            response_headers[h.title()] = upstream.headers[h]

    async def body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        except httpx.HTTPError as exc:
            # The source CDN dropped the connection mid-stream - nothing to do but stop;
            # headers are already sent so we can't turn this into a clean HTTP error.
            print(f"[stream] {track_id} connection to source dropped: {exc}")
        finally:
            await upstream.aclose()
            await hc.aclose()

    return StreamingResponse(
        body(), status_code=upstream.status_code, media_type=media_type, headers=response_headers
    )


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
