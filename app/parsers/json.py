import json
from typing import Any

from app.config import SourceConfig
from app.models import Item
from app.parsers.common import make_item


def _read_path(value: Any, path: str | None) -> Any:
    if not path:
        return None
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def parse_json(source: SourceConfig, payload: bytes | str) -> list[Item]:
    fields = source.fields
    if fields is None:
        raise ValueError(f"JSON fields are missing for {source.name}")

    data = json.loads(payload)
    records = _read_path(data, source.item_path) if source.item_path else data
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise ValueError(f"JSON item path for {source.name} must resolve to a list")

    items: list[Item] = []
    for record in records:
        link = _read_path(record, fields.link)
        if not link and fields.link_template and isinstance(record, dict):
            try:
                link = fields.link_template.format(**record)
            except (KeyError, IndexError, ValueError):
                link = None
        item = make_item(
            source_name=source.name,
            base_url=source.url,
            title=_read_path(record, fields.title),
            link=link,
            price=_read_path(record, fields.price),
            currency=_read_path(record, fields.currency) or source.currency,
            image=_read_path(record, fields.image),
        )
        if item is not None:
            items.append(item)
    return items
