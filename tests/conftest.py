from decimal import Decimal
from pathlib import Path

import pytest

from app.config import SourceConfig
from app.models import Item, PriceDrop
from app.storage import Storage

FIXTURES = Path(__file__).parent / "fixtures"


def make_item(
    url: str = "https://shop.example/item/1",
    price: str | None = "100",
    title: str = "Test item",
    source: str = "Test shop",
) -> Item:
    from app.parsers.common import make_item as build

    item = build(source_name=source, base_url=url, title=title, link=url, price=price)
    assert item is not None
    return Item(
        id=item.id,
        title=item.title,
        price=Decimal(price) if price is not None else None,
        currency="USD",
        url=item.url,
        image=None,
        source=source,
    )


def make_source(**overrides) -> SourceConfig:
    data = {
        "name": "Test shop",
        "url": "https://shop.example/search",
        "type": "html",
        "interval_minutes": 10,
        "selectors": {"item": ".listing", "title": ".t", "link": "a"},
    }
    data.update(overrides)
    return SourceConfig.model_validate(data)


class FakeNotifier:
    def __init__(self) -> None:
        self.new: list[Item] = []
        self.drops: list[PriceDrop] = []
        self.admin: list[str] = []

    async def send_new(self, item: Item) -> None:
        self.new.append(item)

    async def send_price_drop(self, drop: PriceDrop) -> None:
        self.drops.append(drop)

    async def send_admin_message(self, text: str) -> None:
        self.admin.append(text)


@pytest.fixture
async def storage(tmp_path) -> Storage:
    db = Storage(str(tmp_path / "monitor.db"))
    await db.initialize()
    return db
