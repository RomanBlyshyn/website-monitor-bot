from decimal import Decimal

from app.config import FiltersConfig
from app.filters import matches_filters
from app.models import Item


def test_filters_apply_keyword_and_price_constraints() -> None:
    item = Item(
        id="item-id",
        title="Refurbished Mechanical Keyboard",
        price=Decimal("120"),
        currency="USD",
        url="https://shop.example/keyboard",
        image=None,
        source="Shop",
    )
    filters = FiltersConfig(
        include_keywords=["keyboard"],
        exclude_keywords=["parts only"],
        min_price=50,
        max_price=200,
    )

    assert matches_filters(item, filters)
    assert not matches_filters(
        item, FiltersConfig(include_keywords=["monitor"])
    )
    assert not matches_filters(
        item, FiltersConfig(exclude_keywords=["KEYBOARD"])
    )
    assert not matches_filters(item, FiltersConfig(min_price=121))
