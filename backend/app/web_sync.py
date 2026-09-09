"""Anonymous channel sync.

Public Telegram channels expose a web preview at https://t.me/s/<channel> that needs
no account. It paginates backwards through `?before=<message_id>`, 20 posts at a time,
and every post carries its id, text, links, and timestamp - everything the player needs
except the ability to react, which stays account-only.
"""

import asyncio

import httpx
from bs4 import BeautifulSoup

from .config import WEB_BASE_URL
from .sync_core import URL_RE, Post, clean_links

PAGE_DELAY = 0.7  # seconds between pages - Telegram throttles impatient clients
REQUEST_TIMEOUT = 20
MAX_PAGES = 2000  # hard stop; ~40k posts, far past any real channel

# A plain default UA gets 403 from time to time; identify ourselves honestly instead.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 radio-dungeon-player"
)


class ChannelUnavailable(RuntimeError):
    pass


def page_url(channel: str, before: int | None = None) -> str:
    url = f"{WEB_BASE_URL}/s/{channel}"
    return f"{url}?before={before}" if before else url


def parse_page(html: str) -> list[Post]:
    """Extract posts from one preview page, oldest first."""
    soup = BeautifulSoup(html, "html.parser")
    posts: list[Post] = []

    for node in soup.select("div.tgme_widget_message[data-post]"):
        raw_id = str(node.get("data-post", "")).rsplit("/", 1)[-1]
        if not raw_id.isdigit():
            continue

        # The link preview block reuses similar classes, so prefer the message body.
        body = node.select_one(".tgme_widget_message_text.js-message_text") or node.select_one(
            ".tgme_widget_message_text"
        )

        text = ""
        links: list[str] = []
        if body is not None:
            for br in body.find_all("br"):
                br.replace_with("\n")
            text = body.get_text().strip()
            # Anchors carry the real target: the channel hyperlinks words rather than
            # pasting bare urls, so the href is the only place the album link exists.
            links.extend(a.get("href", "") for a in body.select("a[href]"))
            links.extend(URL_RE.findall(text))

        preview = node.select_one("a.tgme_widget_message_link_preview[href]")
        if preview is not None:
            links.append(preview.get("href", ""))

        time_node = node.select_one("time[datetime]")
        date = time_node.get("datetime") if time_node is not None else None

        posts.append(Post(id=int(raw_id), text=text, date=date, links=clean_links(links)))

    posts.sort(key=lambda p: p.id)
    return posts


async def _get(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    if response.status_code == 404:
        raise ChannelUnavailable(
            f"{url} returned 404 - check the channel name in TG_CHANNEL"
        )
    if response.status_code != 200:
        raise ChannelUnavailable(f"{url} returned HTTP {response.status_code}")
    return response.text


async def fetch_posts(channel: str, last_id: int) -> list[Post]:
    """Walk the preview backwards until we reach posts we already have."""
    collected: dict[int, Post] = {}
    before: int | None = None

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en,ru;q=0.9"},
    ) as client:
        for page_no in range(MAX_PAGES):
            page = parse_page(await _get(client, page_url(channel, before)))
            if not page:
                if page_no == 0:
                    raise ChannelUnavailable(
                        f"no posts found at {page_url(channel)} - the channel is private "
                        "or has its web preview disabled, which needs TG_MODE=account"
                    )
                break

            for post in page:
                if post.id > last_id:
                    collected[post.id] = post

            oldest = page[0].id
            if oldest <= last_id or oldest <= 1:
                break
            if before is not None and oldest >= before:
                # Pagination stopped moving - bail out rather than loop forever.
                break
            before = oldest

            print(f"[sync] read page {page_no + 1}, {len(collected)} new post(s) so far")
            await asyncio.sleep(PAGE_DELAY)

    return [collected[k] for k in sorted(collected)]
