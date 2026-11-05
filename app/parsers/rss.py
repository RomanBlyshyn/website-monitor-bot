import feedparser
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.config import SourceConfig
from app.models import Item
from app.parsers.common import make_item


def parse_rss(source: SourceConfig, payload: bytes | str) -> list[Item]:
    feed = feedparser.parse(payload)
    items: list[Item] = []
    for entry in feed.entries:
        link = entry.get("link")
        if not link:
            link = next(
                (
                    candidate.get("href")
                    for candidate in entry.get("links", [])
                    if candidate.get("rel") == "alternate"
                ),
                None,
            )

        image = None
        enclosures = entry.get("enclosures", [])
        if enclosures:
            image = enclosures[0].get("href")
        if image is None and entry.get("summary"):
            image_node = HTMLParser(entry.summary).css_first("img")
            if image_node is not None:
                image = image_node.attributes.get("src")

        price = entry.get("price")
        if price is None and entry.get("price_detail"):
            price = entry.price_detail.get("amount")
        item = make_item(
            source_name=source.name,
            base_url=source.url,
            title=entry.get("title"),
            link=link,
            price=price,
            currency=entry.get("currency") or source.currency,
            image=image,
        )
        if item is not None:
            items.append(item)
    return items
