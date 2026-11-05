import asyncio
import logging
import random
from typing import Protocol

from app.config import SourceConfig
from app.fetchers.browser import BrowserFetcher
from app.fetchers.http import HttpFetcher
from app.filters import matches_filters
from app.models import Item, PriceDrop
from app.parsers.html import parse_html
from app.parsers.json import parse_json
from app.parsers.rss import parse_rss
from app.storage import Storage

logger = logging.getLogger(__name__)

FAILURE_ALERT_THRESHOLD = 3


class Notifier(Protocol):
    async def send_new(self, item: Item) -> None: ...
    async def send_price_drop(self, drop: PriceDrop) -> None: ...
    async def send_admin_message(self, text: str) -> None: ...


def next_delay(interval_minutes: int) -> float:
    """Interval in seconds plus 10–30% random jitter."""
    return interval_minutes * 60 * (1 + random.uniform(0.1, 0.3))


class MonitorScheduler:
    def __init__(
        self,
        sources: list[SourceConfig],
        storage: Storage,
        notifier: Notifier,
        http_fetcher: HttpFetcher,
        browser_fetcher: BrowserFetcher | None,
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
        async with asyncio.TaskGroup() as tasks:
            for index, source in enumerate(self.sources):
                tasks.create_task(
                    self._run_source(source, start_delay=index * 2.0),
                    name=f"source:{source.name}",
                )

    async def _run_source(self, source: SourceConfig, start_delay: float) -> None:
        await asyncio.sleep(start_delay)  # Spread out the first requests.
        while True:
            await self.monitor_enabled.wait()
            await self.check_once(source)
            delay = next_delay(source.interval_minutes)
            logger.debug("Next check of %s in %.0fs", source.name, delay)
            await asyncio.sleep(delay)

    async def check_once(self, source: SourceConfig) -> None:
        """Fetch, parse, store and notify for one source. Never raises."""
        try:
            items = await self._fetch_items(source)
            new_items, price_drops, baseline = await self.storage.process_items(
                source.name, items
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._handle_failure(source, error)
            return

        if await self.storage.record_success(source.name):
            logger.info("Source %s recovered", source.name)
            await self.notifier.send_admin_message(f"✅ Source recovered: {source.name}")

        if baseline:
            logger.info(
                "Baseline saved for %s: %s items (no alerts on first run)",
                source.name,
                len(items),
            )
            return

        sent = 0
        for item in new_items:
            if matches_filters(item, source.filters):
                await self.notifier.send_new(item)
                sent += 1
        for drop in price_drops:
            if matches_filters(drop.item, source.filters):
                await self.notifier.send_price_drop(drop)
                sent += 1
        logger.info(
            "Checked %s: %s items, %s new, %s price drops, %s alerts queued",
            source.name,
            len(items),
            len(new_items),
            len(price_drops),
            sent,
        )

    async def _handle_failure(self, source: SourceConfig, error: Exception) -> None:
        message = f"{type(error).__name__}: {error}"
        failures, should_notify = await self.storage.record_failure(
            source.name, message, threshold=FAILURE_ALERT_THRESHOLD
        )
        logger.error(
            "Source %s failed (%s in a row): %s", source.name, failures, message
        )
        if should_notify:
            await self.notifier.send_admin_message(
                f"⚠️ Source failed {failures} times in a row: {source.name}\n"
                f"Latest error: {message}"
            )

    async def _fetch_items(self, source: SourceConfig) -> list[Item]:
        if source.respect_robots:
            await self.http_fetcher.ensure_allowed(source.url)

        if source.type == "html":
            if source.use_browser:
                if self.browser_fetcher is None:
                    raise RuntimeError("Browser fetcher is not available")
                html = await self.browser_fetcher.fetch(source.url)
            else:
                html = (await self.http_fetcher.fetch(source.url)).decode(
                    "utf-8", errors="replace"
                )
            items = parse_html(source, html)
        else:
            payload = await self.http_fetcher.fetch(source.url)
            if source.type == "rss":
                items = parse_rss(source, payload)
            else:
                items = parse_json(source, payload)

        if not items:
            raise ValueError("No items parsed; check the selectors or field paths")
        return items
