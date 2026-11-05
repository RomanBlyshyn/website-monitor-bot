from pathlib import Path

from app.config import SourceConfig
from app.parsers.html import parse_html


def test_html_parser_reads_saved_fixture() -> None:
    source = SourceConfig.model_validate(
        {
            "name": "Fixture shop",
            "url": "https://shop.example/search",
            "type": "html",
            "interval_minutes": 10,
            "selectors": {
                "item": ".listing",
                "title": ".listing-title",
                "price": ".listing-price",
                "link": ".listing-link",
                "image": ".listing-image",
            },
        }
    )
    html = (Path(__file__).parent / "fixtures" / "listings.html").read_text(
        encoding="utf-8"
    )

    items = parse_html(source, html)

    assert len(items) == 2
    assert items[0].title == "Mechanical Keyboard"
    assert str(items[0].price) == "129.99"
    assert items[0].currency == "USD"
    assert items[0].url == "https://shop.example/item/keyboard"
    assert items[0].image == "https://shop.example/images/keyboard.jpg"
