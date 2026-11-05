import re

from selectolax.lexbor import LexborHTMLParser, LexborNode

from app.config import SourceConfig
from app.models import Item
from app.parsers.common import make_item

_ATTR_SUFFIX = re.compile(r"^(?P<css>.*?)\s*::attr\((?P<attr>[\w:-]+)\)\s*$")
_IMAGE_ATTRS = ("src", "data-src", "data-lazy-src")


def _select(
    node: LexborNode, selector: str | None, default_attrs: tuple[str, ...] = ()
) -> str | None:
    """Read text (or an attribute) from the first match of ``selector``."""
    if not selector:
        return None

    attr = None
    match = _ATTR_SUFFIX.match(selector)
    if match:
        selector, attr = match["css"], match["attr"]

    target = node if selector in ("", ":scope") else node.css_first(selector)
    if target is None:
        return None

    for name in (attr,) if attr else default_attrs:
        value = target.attributes.get(name)
        if value:
            return value
    if attr:
        return None
    return target.text(strip=True) or None


def parse_html(source: SourceConfig, html: str) -> list[Item]:
    selectors = source.selectors
    if selectors is None:
        raise ValueError(f"HTML selectors are missing for {source.name}")

    document = LexborHTMLParser(html)
    items: list[Item] = []
    for node in document.css(selectors.item):
        item = make_item(
            source_name=source.name,
            base_url=source.url,
            title=_select(node, selectors.title),
            link=_select(node, selectors.link, ("href",)),
            price=_select(node, selectors.price),
            currency=source.currency,
            image=_select(node, selectors.image, _IMAGE_ATTRS),
        )
        if item is not None:
            items.append(item)
    return items
