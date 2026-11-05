import hashlib
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urldefrag, urljoin

from app.models import Item

_CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₴": "UAH",
    "¥": "JPY",
}


def parse_price(value: object) -> tuple[Decimal | None, str]:
    text = str(value or "").strip()
    if not text:
        return None, ""

    currency = next(
        (code for symbol, code in _CURRENCY_SYMBOLS.items() if symbol in text),
        "",
    )
    if not currency:
        currency_match = re.search(r"\b[A-Z]{3}\b", text.upper())
        if currency_match:
            currency = currency_match.group(0)

    number_match = re.search(r"\d[\d.,\s]*\d|\d", text)
    if not number_match:
        return None, currency

    number = re.sub(r"\s", "", number_match.group(0))
    if "," in number and "." in number:
        decimal_separator = "," if number.rfind(",") > number.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        number = number.replace(thousands_separator, "")
        number = number.replace(decimal_separator, ".")
    elif "," in number or "." in number:
        separator = "," if "," in number else "."
        parts = number.split(separator)
        if len(parts) > 2:
            number = "".join(parts[:-1]) + "." + parts[-1]
        elif len(parts[-1]) == 3:
            number = "".join(parts)
        else:
            number = number.replace(separator, ".")

    try:
        return Decimal(number), currency
    except InvalidOperation:
        return None, currency


def normalize_url(base_url: str, value: str) -> str:
    absolute_url = urljoin(base_url, value.strip())
    return urldefrag(absolute_url)[0]


def make_item(
    *,
    source_name: str,
    base_url: str,
    title: object,
    link: object,
    price: object = None,
    currency: object = "",
    image: object = None,
) -> Item | None:
    title_text = str(title or "").strip()
    link_text = str(link or "").strip()
    if not title_text or not link_text:
        return None

    url = normalize_url(base_url, link_text)
    parsed_price, parsed_currency = parse_price(price)
    resolved_image = (
        normalize_url(base_url, str(image))
        if image and str(image).strip()
        else None
    )
    return Item(
        id=hashlib.sha256(url.encode("utf-8")).hexdigest(),
        title=title_text,
        price=parsed_price,
        currency=str(currency or parsed_currency or "").strip().upper(),
        url=url,
        image=resolved_image,
        source=source_name,
    )
