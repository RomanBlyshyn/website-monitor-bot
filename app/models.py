from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    title: str
    price: Decimal | None
    currency: str
    url: str
    image: str | None
    source: str


@dataclass(frozen=True, slots=True)
class PriceDrop:
    item: Item
    old_price: Decimal
    new_price: Decimal


@dataclass(frozen=True, slots=True)
class Notification:
    text: str
    url: str
    image: str | None = None
    chat_id: int | None = None
