import asyncio

import pytest

from app.scheduler import MonitorScheduler, next_delay
from conftest import FakeNotifier, make_source

PAGE = """
<div class="listing"><a href="/1"><span class="t">Keyboard</span></a><b>$100</b></div>
<div class="listing"><a href="/2"><span class="t">Mouse</span></a><b>$20</b></div>
"""


class FakeFetcher:
    """Serves queued responses; an Exception instance is raised instead."""

    def __init__(self) -> None:
        self.responses: list[str | Exception] = []
        self.robots_checked = 0

    async def ensure_allowed(self, url: str) -> None:
        self.robots_checked += 1

    async def fetch(self, url: str) -> bytes:
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response.encode()


def listing(n: int, title: str, price: int) -> str:
    return f'<div class="listing"><a href="/{n}"><span class="t">{title}</span></a><b>${price}</b></div>'


@pytest.fixture
def setup(storage):
    source = make_source(
        selectors={"item": ".listing", "title": ".t", "link": "a", "price": "b"},
        filters={"exclude_keywords": ["broken"], "max_price": 500},
    )
    fetcher = FakeFetcher()
    notifier = FakeNotifier()
    scheduler = MonitorScheduler(
        [source], storage, notifier, fetcher, None, asyncio.Event()
    )
    return scheduler, source, fetcher, notifier


async def test_baseline_then_new_listing_then_price_drop(setup) -> None:
    scheduler, source, fetcher, notifier = setup
    fetcher.responses = [
        PAGE,
        PAGE + listing(3, "Monitor", 300),
        PAGE.replace("$100", "$75") + listing(3, "Monitor", 300),
    ]

    await scheduler.check_once(source)  # baseline
    assert notifier.new == [] and notifier.drops == []

    await scheduler.check_once(source)
    assert [item.title for item in notifier.new] == ["Monitor"]

    await scheduler.check_once(source)
    assert len(notifier.new) == 1
    assert [(d.item.title, d.old_price, d.new_price) for d in notifier.drops] == [
        ("Keyboard", 100, 75)
    ]
    assert fetcher.robots_checked == 3


async def test_filters_apply_to_new_listings(setup) -> None:
    scheduler, source, fetcher, notifier = setup
    fetcher.responses = [
        PAGE,
        PAGE + listing(3, "Broken monitor", 50) + listing(4, "Gaming PC", 900)
        + listing(5, "Webcam", 40),
    ]

    await scheduler.check_once(source)
    await scheduler.check_once(source)

    assert [item.title for item in notifier.new] == ["Webcam"]


async def test_three_failures_alert_admin_then_recovered(setup) -> None:
    scheduler, source, fetcher, notifier = setup
    fetcher.responses = [PAGE] + [RuntimeError("HTTP 503")] * 4 + [PAGE]

    for _ in range(6):
        await scheduler.check_once(source)  # must never raise

    assert len(notifier.admin) == 2
    assert "failed 3 times in a row" in notifier.admin[0]
    assert "HTTP 503" in notifier.admin[0]
    assert "recovered" in notifier.admin[1]


async def test_empty_page_counts_as_failure(setup) -> None:
    scheduler, source, fetcher, notifier = setup
    fetcher.responses = ["<html></html>"]

    await scheduler.check_once(source)

    status = await scheduler.storage.get_status()
    assert status[0]["consecutive_failures"] == 1
    assert "No items parsed" in status[0]["last_error"]


async def test_one_failing_source_does_not_block_others(storage) -> None:
    good = make_source(name="Good", selectors={"item": ".listing", "title": ".t", "link": "a"})
    bad = make_source(name="Bad")
    fetcher = FakeFetcher()
    fetcher.responses = [RuntimeError("down"), PAGE]
    scheduler = MonitorScheduler(
        [bad, good], storage, FakeNotifier(), fetcher, None, asyncio.Event()
    )

    await scheduler.check_once(bad)
    await scheduler.check_once(good)

    status = {row["source"]: row for row in await storage.get_status()}
    assert status["Bad"]["consecutive_failures"] == 1
    assert status["Good"]["item_count"] == 2


def test_delay_has_10_to_30_percent_jitter() -> None:
    delays = [next_delay(10) for _ in range(500)]
    assert all(660 <= d <= 780 for d in delays)
    assert max(delays) - min(delays) > 60  # actually random
