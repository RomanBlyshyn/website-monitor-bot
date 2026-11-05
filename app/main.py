import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot_commands import create_router
from app.config import get_settings, load_sources
from app.fetchers.browser import BrowserFetcher
from app.fetchers.http import HttpFetcher
from app.notifier import TelegramNotifier
from app.scheduler import MonitorScheduler
from app.storage import Storage


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sources = load_sources()
    storage = Storage(settings.DB_PATH)
    await storage.initialize()

    bot = Bot(token=settings.BOT_TOKEN)
    notifier = TelegramNotifier(bot, settings.CHAT_ID, settings.ADMIN_CHAT_ID)
    notifier.start()
    monitor_enabled = asyncio.Event()
    monitor_enabled.set()

    http_fetcher = HttpFetcher()
    browser_fetcher = BrowserFetcher()
    scheduler = MonitorScheduler(
        sources=sources,
        storage=storage,
        notifier=notifier,
        http_fetcher=http_fetcher,
        browser_fetcher=browser_fetcher,
        monitor_enabled=monitor_enabled,
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(
        create_router(
            settings.ADMIN_CHAT_ID,
            sources,
            storage,
            monitor_enabled,
        )
    )

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(scheduler.run(), name="monitor-scheduler")
            tasks.create_task(dispatcher.start_polling(bot), name="telegram-polling")
    finally:
        await notifier.close()
        await http_fetcher.close()
        await browser_fetcher.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
