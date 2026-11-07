from datetime import datetime, timezone

from app.bot_commands import describe_filters, format_checked
from app.config import FiltersConfig

NOW = datetime(2026, 11, 7, 15, 45, 50, tzinfo=timezone.utc)


def test_format_checked_is_human_readable() -> None:
    assert format_checked("2026-11-07T15:42:50+00:00", NOW) == "2026-11-07 15:42 UTC (3 min ago)"
    assert format_checked("2026-11-07T15:45:30+00:00", NOW).endswith("(just now)")
    assert format_checked("2026-11-07T10:45:50+00:00", NOW).endswith("(5 h ago)")
    assert format_checked(None, NOW) == "not checked yet"


def test_describe_filters() -> None:
    assert describe_filters(
        FiltersConfig(exclude_keywords=["sample"], min_price=10, max_price=60)
    ) == ["exclude: sample", "price: 10–60"]
    assert describe_filters(FiltersConfig(max_price=2500)) == ["price ≤ 2500"]
    assert describe_filters(FiltersConfig(min_price=9.5)) == ["price ≥ 9.5"]
    assert describe_filters(FiltersConfig()) == []
