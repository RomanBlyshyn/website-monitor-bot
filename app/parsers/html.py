from selectolax.parser import HTMLParser

from app.config import SourceConfig
from app.models import Item
from app.parsers.common import make_item


def parse_html(source: SourceConfig, html: str) -> list[Item]:
    selectors = source.selectors
    if selectors is None:
        raise ValueError(f"HTML selectors are missing for {source.name}")

    document = HTMLParser(html)
    items: list[Item] = []
    for node in document.css(selectors.item):
        title_node = node if selectors.title == ":scope" else node.css_first(selectors.title)
        link_node = node if selectors.link == ":scope" else node.css_first(selectors.link)
        price_node = (
            node.css_first(selectors.price) if selectors.price is not None else None
        )
        image_node = (
            node.css_first(selectors.image) if selectors.image is not None else None
        )
        if title_node is None or link_node is None:
            continue

        link = link_node.attributes.get("href") or link_node.text(strip=True)
        image = None
        if image_node is not None:
            image = (
                image_node.attributes.get("src")
                or image_node.attributes.get("data-src")
                or image_node.attributes.get("data-lazy-src")
            )
        item = make_item(
            source_name=source.name,
            base_url=source.url,
            title=title_node.text(strip=True),
            link=link,
            price=price_node.text(strip=True) if price_node is not None else None,
            currency=source.currency,
            image=image,
        )
        if item is not None:
            items.append(item)
    return items
