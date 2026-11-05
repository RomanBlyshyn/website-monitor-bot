from decimal import Decimal

from app.config import FiltersConfig
from app.models import Item


def matches_filters(item: Item, filters: FiltersConfig) -> bool:
    title = item.title.casefold()
    if filters.include_keywords and not any(
        keyword.casefold() in title for keyword in filters.include_keywords
    ):
        return False
    if any(keyword.casefold() in title for keyword in filters.exclude_keywords):
        return False

    if filters.min_price is not None:
        if item.price is None or item.price < Decimal(str(filters.min_price)):
            return False
    if filters.max_price is not None:
        if item.price is None or item.price > Decimal(str(filters.max_price)):
            return False
    return True
