import json
from decimal import Decimal

import pytest

from app.parsers.common import make_item, parse_price
from app.parsers.html import parse_html
from app.parsers.json import parse_json
from app.parsers.rss import parse_rss
from conftest import FIXTURES, make_source


def test_html_parser_on_saved_books_page() -> None:
    source = make_source(
        name="Books",
        url="https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
        currency="GBP",
        selectors={
            "item": "article.product_pod",
            "title": "h3 a::attr(title)",
            "link": "h3 a",
            "price": "p.price_color",
            "image": "div.image_container img",
        },
    )
    html = (FIXTURES / "books_mystery.html").read_text(encoding="utf-8")

    items = parse_html(source, html)

    assert len(items) == 20
    first = items[0]
    assert first.title == "Sharp Objects"  # full title from the attribute, not "..."
    assert first.price == Decimal("47.82")
    assert first.currency == "GBP"
    assert first.url == "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"
    assert first.image.startswith("https://books.toscrape.com/media/cache/")
    assert len({item.id for item in items}) == 20


def test_html_parser_on_generic_fixture() -> None:
    source = make_source(
        selectors={
            "item": ".listing",
            "title": ".listing-title",
            "price": ".listing-price",
            "link": ".listing-link",
            "image": ".listing-image",
        },
    )
    html = (FIXTURES / "listings.html").read_text(encoding="utf-8")

    items = parse_html(source, html)

    assert [item.title for item in items] == ["Mechanical Keyboard", "Wireless Mouse"]
    assert items[0].price == Decimal("129.99") and items[0].currency == "USD"
    assert items[1].price == Decimal("24.50") and items[1].currency == "EUR"
    assert items[0].url == "https://shop.example/item/keyboard"
    assert items[0].image == "https://shop.example/images/keyboard.jpg"
    assert items[1].image is None


def test_items_without_title_or_link_are_skipped() -> None:
    source = make_source()
    html = """
      <div class="listing"><span class="t">No link</span></div>
      <div class="listing"><a href="/x"></a></div>
      <div class="listing"><a href="/ok"><span class="t">Ok</span></a></div>
    """
    assert [item.title for item in parse_html(source, html)] == ["Ok"]


@pytest.mark.parametrize(
    ("raw", "price", "currency"),
    [
        ("$1,299.99", "1299.99", "USD"),
        ("1.299,99 €", "1299.99", "EUR"),
        ("£47.82", "47.82", "GBP"),
        ("12 500 UAH", "12500", "UAH"),
        ("1 200,50 ₴", "1200.50", "UAH"),
        ("19.5", "19.5", ""),
        (1999.99, "1999.99", ""),
        ("Free", None, ""),
        ("", None, ""),
    ],
)
def test_parse_price(raw, price, currency) -> None:
    value, code = parse_price(raw)
    assert value == (Decimal(price) if price else None)
    assert code == currency


def test_item_id_is_hash_of_absolute_url() -> None:
    a = make_item(source_name="s", base_url="https://x.com/list", title="A", link="/item/1")
    b = make_item(
        source_name="s", base_url="https://x.com/", title="B", link="https://x.com/item/1#top"
    )
    assert a.url == b.url == "https://x.com/item/1"
    assert a.id == b.id and len(a.id) == 64


def test_json_parser_with_paths_and_link_template() -> None:
    source = make_source(
        type="json",
        url="https://api.example/products",
        selectors=None,
        item_path="data.products",
        fields={
            "title": "title",
            "price": "pricing.amount",
            "image": "images.0",
            "link_template": "https://shop.example/p/{id}",
        },
        currency="USD",
    )
    payload = json.dumps(
        {
            "data": {
                "products": [
                    {"id": 7, "title": "Laptop", "pricing": {"amount": 999.5}, "images": ["/7.jpg"]},
                    {"id": 8, "title": "", "pricing": {"amount": 1}},
                ]
            }
        }
    )

    items = parse_json(source, payload)

    assert len(items) == 1
    assert items[0].url == "https://shop.example/p/7"
    assert items[0].price == Decimal("999.5")
    assert items[0].image == "https://api.example/7.jpg"


def test_rss_parser_reads_atom_feed() -> None:
    source = make_source(type="rss", url="https://github.com/o/r/releases.atom", selectors=None)
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Releases</title>
      <entry>
        <id>1</id><title>v1.2.0</title>
        <link rel="alternate" href="https://github.com/o/r/releases/tag/v1.2.0"/>
        <content type="html">&lt;img src="/banner.png"&gt; notes</content>
      </entry>
    </feed>"""

    items = parse_rss(source, feed)

    assert len(items) == 1
    assert items[0].title == "v1.2.0"
    assert items[0].url == "https://github.com/o/r/releases/tag/v1.2.0"
    assert items[0].price is None
    assert items[0].image == "https://github.com/banner.png"
