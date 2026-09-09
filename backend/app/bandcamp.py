"""Pull playable mp3 urls straight off a bandcamp page.

The desktop player resolves a stream through yt-dlp on every play, because bandcamp's
urls expire. The web build does it ahead of time instead: bandcamp hands out mp3-128
urls that stay valid for exactly 24 hours, so a scheduled rebuild keeps them fresh and
the listener's browser streams straight from bandcamp - no audio passes through us.

Every album page carries a `data-tralbum` blob: real JSON with one entry per track,
including its stream url. That means one request per album rather than one per track,
and no regex guessing against markup.
"""

import html as htmlmod
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

# Bandcamp stamps every stream url with the moment it stops working.
STREAM_TTL_SECONDS = 24 * 60 * 60

_TRALBUM_RE = re.compile(r'data-tralbum="([^"]+)"')
_OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]+)"')


class NotBandcamp(ValueError):
    """The page carries no tralbum data - not a bandcamp album/track page."""


@dataclass
class BcTrack:
    """One streamable track, as the web player needs it."""

    webpage_url: str  # the track's own page - doubles as the "buy on bandcamp" link
    title: str
    artist: str
    stream_url: str
    duration: float | None = None
    thumbnail: str | None = None
    album_url: str | None = None


@dataclass
class BcAlbum:
    url: str
    title: str = ""
    artist: str = ""
    thumbnail: str | None = None
    tracks: list[BcTrack] = field(default_factory=list)


def stream_expiry(stream_url: str) -> int | None:
    """Unix time the url stops working, read from its own `ts` parameter."""
    m = re.search(r"[?&]ts=([0-9]+)", stream_url)
    return int(m.group(1)) if m else None


def parse_page(html: str, page_url: str) -> BcAlbum:
    """Read an album (or single-track) page into its streamable tracks."""
    m = _TRALBUM_RE.search(html)
    if not m:
        raise NotBandcamp(f"no data-tralbum on {page_url}")

    blob = json.loads(htmlmod.unescape(m.group(1)))
    current = blob.get("current") or {}

    art = _OG_IMAGE_RE.search(html)
    album = BcAlbum(
        url=blob.get("url") or page_url,
        title=current.get("title") or "",
        artist=blob.get("artist") or "",
        thumbnail=art.group(1) if art else None,
    )

    for entry in blob.get("trackinfo") or []:
        # `streaming` is 0 for preorder-only or artist-disabled tracks; those have no
        # playable file at all, so there is nothing to offer the browser.
        if not entry.get("streaming"):
            continue
        stream_url = (entry.get("file") or {}).get("mp3-128")
        if not stream_url:
            continue

        link = entry.get("title_link")
        album.tracks.append(
            BcTrack(
                webpage_url=urljoin(album.url, link) if link else album.url,
                title=entry.get("title") or "",
                # Compilations set a per-track artist; everything else inherits the album's.
                artist=entry.get("artist") or album.artist,
                stream_url=stream_url,
                duration=entry.get("duration"),
                thumbnail=album.thumbnail,
                album_url=album.url,
            )
        )

    return album


def album_url_from_track_page(html: str, page_url: str) -> str | None:
    """Find which album a track page belongs to.

    Only needed to backfill tracks discovered before album urls were recorded - once
    known, refreshes fetch the album directly and get every track in one request.
    """
    try:
        blob = json.loads(htmlmod.unescape(_TRALBUM_RE.search(html).group(1)))
    except (AttributeError, ValueError):
        return None

    for key in ("album_url", "url"):
        value = (blob.get("current") or {}).get(key) or blob.get(key)
        if value and "/album/" in value:
            return urljoin(page_url, value)

    m = re.search(r'<a[^>]+href="(/album/[^"]+)"', html)
    return urljoin(page_url, m.group(1)) if m else None
