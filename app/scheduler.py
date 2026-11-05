import asyncio
import logging
import random

from app.config import SourceConfig
from app.fetchers.browser import BrowserFetcher
from app.fetchers.http import HttpFetcher
from app.filters import matches_filters
from app.models import Item
from app.notifier import TelegramNotifier
from app.parsers.html import parse_html
from app.parsers.json import parse_json
from app.parsers.rss import parse_rss
from app.storage import Storage

logger = logging.getLogger(__name__)


class MonitorScheduler:
    def __init__(
        self,
        sources: list[SourceConfig],
        storage: Storage,
        notifier: TelegramNotifier,
        http_fetcher: HttpFetcher,
        browser_fetcher: BrowserFetcher,
        monitor_enabled: asyncio.Event,
    ) -> None:
        self.sources = sources
        self.storage = storage
        self.notifier = notifier
        self.http_fetcher = http_fetcher
        self.browser_fetcher = browser_fetcher
        self.monitor_enabled = monitor_enabled

    async def run(self) -> None:
        await self.storage.register_sources([source.name for source in self.sources])
        tasks = [
            asyncio.create_task(self._run_source(source), name=f"source:{source.name}")
            for source in self.sources
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_source(self, source: SourceConfig) -> None:
        while True:
            await self.monitor_enabled.wait()
            try:
                items = await self._check_source(source)
                new_items, price_drops, baseline = await self.storage.process_items(
                    source.name, items
                )
                recovered = await self.storage.record_success(source.name)
                if recovered:
                    await self.notifier.send_admin_message(
                        f"Source recovered: {source.name}"
                    )
                if baseline:
                    logger.info(
                        "Baseline saved for source %s (%s items)",
                        source.name,
                        len(items),
                    )
                else:
                    for item in new_items:
                        if matches_filters(item, source.filters):
                            await self.notifier.send_new(item)
                    for drop in price_drops:
                        if matches_filters(drop.item, source.filters):
                            await self.notifier.send_price_drop(drop)
                logger.info("Checked source %s: %s items", source.name, len(items))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                failures, should_notify = await self.storage.record_failure(
                    source.name, str(error)
                )
                logger.exception(
                    "Source %s failed (%s consecutive failures)",
                    source.name,
                    failures,
                )
                if should_notify:
                    await self.notifier.send_admin_message(
                        f"Source failed 3 times in a row: {source.name}. "
                        f"Latest error: {error}"
                    )

            jitter = random.uniform(0.1, 0.3)
            delay = source.interval_minutes * 60 * (1 + jitter)
            try:
                await asyncio.wait_for(self.monitor_enabled.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def _check_source(self, source: SourceConfig) -> list[Item]:
        if source.type == "html":
            if source.use_browser:
                payload = await self.browser_fetcher.fetch(source.url)
            else:
                payload = (await self.http_fetcher.fetch(source.url)).decode(
                    "utf-8", errors="replace"
                )
            return parse_html(source, payload)

        payload = await self.http_fetcher.fetch(source.url)
        if source.type == "rss":
            return parse_rss(source, payload)
        return parse_json(source, payload)
