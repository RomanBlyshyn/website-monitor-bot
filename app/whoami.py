"""Print chat IDs that recently messaged the bot (helper for filling .env).

Usage: send any message to your bot in Telegram, then run
    uv run python -m app.whoami
"""

import asyncio
import os

from aiogram import Bot
from dotenv import dotenv_values


async def main() -> None:
    token = os.environ.get("BOT_TOKEN") or dotenv_values(".env").get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN is not set in the environment or .env")

    async with Bot(token=token) as bot:
        me = await bot.get_me()
        updates = await bot.get_updates(limit=100, timeout=0)

    chats = {}
    for update in updates:
        message = update.message or update.channel_post
        if message is not None:
            chat = message.chat
            chats[chat.id] = chat.username or chat.title or chat.full_name

    if not chats:
        print(f"No messages yet. Send /start to @{me.username} and run this again.")
        return
    print(f"Chats that messaged @{me.username}:")
    for chat_id, name in chats.items():
        print(f"  {chat_id}\t{name}")
    print("Put the ID into CHAT_ID and ADMIN_CHAT_ID in .env")


if __name__ == "__main__":
    asyncio.run(main())
