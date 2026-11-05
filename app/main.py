import asyncio
import contextlib
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeChat

from app.bot_commands import create_router
from app.config import get_settings, load_sources
from app.fetchers.http import HttpFetcher
from app.notifier import TelegramNotifier
from app.scheduler import MonitorScheduler
from app.storage import Storage

logger = logging.getLogger("app")

COMMANDS = [
    BotCommand(command="status", description="Sources, last check, items, errors"),
    BotCommand(command="sources", description="Active sources and filters"),
    BotCommand(command="pause", description="Pause monitoring"),
    BotCommand(command="resume", description="Resume monitoring"),
]


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    sources = load_sources(settings.SOURCES_PATH)
    logger.info("Loaded %s sources: %s", len(sources), ", ".join(s.name for s in sources))
    storage = Storage(settings.DB_PATH)
    await storage.initialize()

    bot = Bot(token=settings.BOT_TOKEN)
    notifier = TelegramNotifier(bot, settings.CHAT_ID, settings.ADMIN_CHAT_ID)
    notifier.start()
    monitor_enabled = asyncio.Event()
    monitor_enabled.set()

    http_fetcher = HttpFetcher(settings.USER_AGENT)
    browser_fetcher = None
    if any(source.use_browser for source in sources):
        from app.fetchers.browser import BrowserFetcher

        browser_fetcher = BrowserFetcher(settings.USER_AGENT)

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
        create_router(settings.ADMIN_CHAT_ID, sources, storage, monitor_enabled)
    )

    with contextlib.suppress(Exception):
        await bot.set_my_commands(
            COMMANDS, scope=BotCommandScopeChat(chat_id=settings.ADMIN_CHAT_ID)
        )

    scheduler_task = asyncio.create_task(scheduler.run(), name="monitor-scheduler")

    def on_scheduler_done(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            logger.error("Scheduler crashed; stopping bot", exc_info=task.exception())
            asyncio.ensure_future(dispatcher.stop_polling())

    scheduler_task.add_done_callback(on_scheduler_done)
    try:
        # start_polling handles SIGINT/SIGTERM and returns on shutdown.
        await dispatcher.start_polling(bot, handle_as_tasks=True)
    finally:
        logger.info("Shutting down")
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        await notifier.close()
        await http_fetcher.close()
        if browser_fetcher is not None:
            await browser_fetcher.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
