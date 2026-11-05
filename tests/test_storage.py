from decimal import Decimal

from app.storage import Storage
from conftest import make_item


async def test_first_run_is_baseline_without_alerts(storage) -> None:
    items = [make_item(f"https://shop.example/{n}") for n in range(5)]

    new, drops, baseline = await storage.process_items("Test shop", items)

    assert baseline
    assert new == [] and drops == []
    status = {row["source"]: row for row in await storage.get_status()}
    assert status["Test shop"]["item_count"] == 5


async def test_new_item_after_baseline_is_reported_once(storage) -> None:
    old = make_item("https://shop.example/old")
    fresh = make_item("https://shop.example/new")
    await storage.process_items("Test shop", [old])

    new, _, baseline = await storage.process_items("Test shop", [old, fresh])
    assert not baseline
    assert [item.url for item in new] == [fresh.url]

    new, _, _ = await storage.process_items("Test shop", [old, fresh])
    assert new == []


async def test_no_duplicates_after_restart(tmp_path) -> None:
    path = str(tmp_path / "monitor.db")
    items = [make_item("https://shop.example/a"), make_item("https://shop.example/b")]

    first = Storage(path)
    await first.initialize()
    await first.process_items("Test shop", items[:1])
    await first.process_items("Test shop", items)

    restarted = Storage(path)  # Simulates a container restart: same DB file.
    await restarted.initialize()
    new, drops, baseline = await restarted.process_items("Test shop", items)

    assert not baseline
    assert new == [] and drops == []


async def test_duplicate_urls_within_one_page_count_once(storage) -> None:
    await storage.process_items("Test shop", [make_item("https://shop.example/a")])
    dup = make_item("https://shop.example/b")

    new, _, _ = await storage.process_items("Test shop", [dup, dup])

    assert len(new) == 1


async def test_price_drop_detected_with_old_and_new_price(storage) -> None:
    url = "https://shop.example/item"
    await storage.process_items("Test shop", [make_item(url, "100")])

    _, drops, _ = await storage.process_items("Test shop", [make_item(url, "100")])
    assert drops == []

    _, drops, _ = await storage.process_items("Test shop", [make_item(url, "80")])
    assert len(drops) == 1
    assert drops[0].old_price == Decimal("100")
    assert drops[0].new_price == Decimal("80")

    # The new price becomes the reference: no repeated alert.
    _, drops, _ = await storage.process_items("Test shop", [make_item(url, "80")])
    assert drops == []


async def test_price_increase_or_missing_price_is_not_a_drop(storage) -> None:
    url = "https://shop.example/item"
    await storage.process_items("Test shop", [make_item(url, "100")])

    _, drops, _ = await storage.process_items("Test shop", [make_item(url, "120")])
    assert drops == []
    _, drops, _ = await storage.process_items("Test shop", [make_item(url, None)])
    assert drops == []
    # Missing price keeps the last known price (120) as the reference.
    _, drops, _ = await storage.process_items("Test shop", [make_item(url, "110")])
    assert [d.old_price for d in drops] == [Decimal("120")]


async def test_sources_are_isolated(storage) -> None:
    item = make_item("https://shop.example/shared")
    await storage.process_items("A", [make_item("https://shop.example/a-only")])

    new, _, baseline = await storage.process_items("B", [item])

    assert baseline and new == []


async def test_failure_streak_alerts_once_and_resets(storage) -> None:
    await storage.register_sources(["Test shop"])

    results = [await storage.record_failure("Test shop", "boom") for _ in range(4)]

    assert results == [(1, False), (2, False), (3, True), (4, False)]
    assert await storage.record_success("Test shop") is True
    assert await storage.record_success("Test shop") is False
    assert await storage.record_failure("Test shop", "again") == (1, False)
