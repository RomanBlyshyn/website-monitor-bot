from decimal import Decimal

import pytest

from app.models import Item
from app.storage import Storage


def make_item(price: str) -> Item:
    url = "https://shop.example/item/1"
    return Item(
        id="stable-url-hash",
        title="Test item",
        price=Decimal(price),
        currency="USD",
        url=url,
        image=None,
        source="Test shop",
    )


@pytest.mark.asyncio
async def test_baseline_deduplication_and_price_drop(tmp_path) -> None:
    storage = Storage(str(tmp_path / "monitor.db"))
    await storage.initialize()

    new, drops, was_baseline = await storage.process_items(
        "Test shop", [make_item("100")]
    )
    assert was_baseline
    assert new == []
    assert drops == []

    new, drops, was_baseline = await storage.process_items(
        "Test shop", [make_item("100")]
    )
    assert not was_baseline
    assert new == []
    assert drops == []

    new, drops, _ = await storage.process_items(
        "Test shop", [make_item("80")]
    )
    assert new == []
    assert len(drops) == 1
    assert drops[0].old_price == Decimal("100")
    assert drops[0].new_price == Decimal("80")
