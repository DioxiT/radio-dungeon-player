"""Account-mode channel sync: reads the channel through a logged-in Telethon client
and can send reactions back to it. See web_sync.py for the anonymous alternative.
"""

from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import MessageEntityTextUrl, ReactionEmoji

from .sync_core import URL_RE, Post, clean_links


def extract_links(message) -> list[str]:
    links = list(URL_RE.findall(message.raw_text or ""))
    if message.entities:
        for entity in message.entities:
            if isinstance(entity, MessageEntityTextUrl):
                links.append(entity.url)
    return clean_links(links)


async def fetch_posts(client, channel: str, last_id: int) -> list[Post]:
    posts = []
    async for msg in client.iter_messages(channel, min_id=last_id, reverse=True, limit=None):
        posts.append(
            Post(
                id=msg.id,
                text=msg.raw_text or "",
                date=msg.date.isoformat() if msg.date else None,
                links=extract_links(msg),
            )
        )
    return posts


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
