import asyncio

from telethon import TelegramClient

from .config import API_HASH, API_ID, SESSION_PATH


async def main():
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"Logged in as {me.first_name} (@{me.username}). Session saved to {SESSION_PATH}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
