import yt_dlp


class _SilentLogger:
    """Dead links (404/removed) are expected and already handled by the caller -
    yt-dlp otherwise prints them as ERROR to stderr even with quiet=True."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


_COMMON_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "socket_timeout": 15,
    "retries": 1,
    "extractor_retries": 1,
    "logger": _SilentLogger(),
}

_PROBE_OPTS = {**_COMMON_OPTS, "extract_flat": "in_playlist", "ignoreerrors": True}

_RESOLVE_OPTS = {**_COMMON_OPTS, "format": "bestaudio/best"}


def probe(url: str) -> list[dict] | None:
    """Return lightweight metadata for a track or every track in an album/playlist."""
    try:
        with yt_dlp.YoutubeDL(_PROBE_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None
    if info is None:
        # ignoreerrors=True makes yt-dlp return None (instead of raising) for
        # fully unavailable links, e.g. a removed video.
        return None

    entries = info.get("entries")
    if entries:
        # Flat album/playlist extraction rarely exposes a pretty uploader name,
        # only the bandcamp subdomain id - best-effort prettify it as a fallback.
        base_artist = info.get("uploader") or info.get("artist")
        if not base_artist and info.get("uploader_id"):
            base_artist = info["uploader_id"].replace("-", " ").replace("_", " ").title()
        base_thumb = info.get("thumbnail")
        results = []
        for e in entries:
            if not e:
                continue
            webpage_url = e.get("url") or e.get("webpage_url")
            if not webpage_url:
                continue
            results.append(
                {
                    "webpage_url": webpage_url,
                    "title": e.get("title") or webpage_url,
                    "artist": e.get("uploader") or base_artist or "",
                    "thumbnail": e.get("thumbnail") or base_thumb,
                }
            )
        return results

    webpage_url = info.get("webpage_url") or url
    return [
        {
            "webpage_url": webpage_url,
            "title": info.get("title") or webpage_url,
            "artist": info.get("uploader") or info.get("artist") or "",
            "thumbnail": info.get("thumbnail"),
        }
    ]


def resolve_stream(webpage_url: str) -> tuple[str, str]:
    """Resolve a fresh, playable direct audio URL. Bandcamp links expire, so call this
    right before streaming rather than caching the result."""
    with yt_dlp.YoutubeDL(_RESOLVE_OPTS) as ydl:
        info = ydl.extract_info(webpage_url, download=False)

    stream_url = info.get("url")
    ext = info.get("ext", "mp3")
    if not stream_url and info.get("formats"):
        fmt = info["formats"][-1]
        stream_url = fmt["url"]
        ext = fmt.get("ext", ext)
    if not stream_url:
        raise ValueError(f"could not resolve a stream url for {webpage_url}")
    return stream_url, ext
