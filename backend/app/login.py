import asyncio
import sys

from telethon import TelegramClient

from .config import API_HASH, API_ID, SESSION_PATH, has_credentials


async def main():
    if not has_credentials():
        print(
            "TG_API_ID / TG_API_HASH are missing from backend/.env.\n"
            "Get them at https://my.telegram.org/apps, or run the player without an "
            "account by setting TG_MODE=anonymous instead."
        )
        sys.exit(1)

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"Logged in as {me.first_name} (@{me.username}). Session saved to {SESSION_PATH}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
