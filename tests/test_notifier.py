from datetime import datetime, timezone
from decimal import Decimal

from app.models import Item, PriceDrop
from app.notifier import format_new_listing, format_price_drop


def item(price: str | None = "1299.99") -> Item:
    return Item(
        id="x",
        title="Laptop <Pro> & Co",
        price=Decimal(price) if price else None,
        currency="USD",
        url="https://shop.example/1",
        image=None,
        source="Shop",
    )


def test_new_listing_message_format() -> None:
    now = datetime(2026, 11, 5, 14, 30, tzinfo=timezone.utc)

    text = format_new_listing(item(), now)

    assert text == (
        "🆕 New listing — Shop\n"
        "<b>Laptop &lt;Pro&gt; &amp; Co</b>\n"
        "💰 1,299.99 USD\n"
        "🕒 2026-11-05 14:30 UTC"
    )


def test_new_listing_without_price() -> None:
    assert "💰 Price not listed" in format_new_listing(item(None))


def test_price_drop_message_format() -> None:
    drop = PriceDrop(item("800"), old_price=Decimal("1000"), new_price=Decimal("800"))

    assert format_price_drop(drop) == (
        "💸 Price drop — Shop\n"
        "<b>Laptop &lt;Pro&gt; &amp; Co</b>\n"
        "<s>1,000</s> → <b>800</b> USD (-20%)"
    )
