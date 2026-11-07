import asyncio
import html
import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import FiltersConfig, SourceConfig
from app.storage import Storage

logger = logging.getLogger(__name__)


def format_checked(value: str | None, now: datetime | None = None) -> str:
    """'2026-11-07T15:42:50+00:00' -> '2026-11-07 15:42 UTC (3 min ago)'."""
    if not value:
        return "not checked yet"
    try:
        checked = datetime.fromisoformat(value)
    except ValueError:
        return value
    now = now or datetime.now(timezone.utc)
    minutes = max(0, int((now - checked).total_seconds() // 60))
    if minutes < 1:
        ago = "just now"
    elif minutes < 60:
        ago = f"{minutes} min ago"
    elif minutes < 48 * 60:
        ago = f"{minutes // 60} h ago"
    else:
        ago = f"{minutes // 1440} days ago"
    return f"{checked.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC ({ago})"


def _number(value: float) -> str:
    return f"{value:g}"


def describe_filters(filters: FiltersConfig) -> list[str]:
    parts = []
    if filters.include_keywords:
        parts.append("include: " + ", ".join(filters.include_keywords))
    if filters.exclude_keywords:
        parts.append("exclude: " + ", ".join(filters.exclude_keywords))
    low, high = filters.min_price, filters.max_price
    if low is not None and high is not None:
        parts.append(f"price: {_number(low)}–{_number(high)}")
    elif low is not None:
        parts.append(f"price ≥ {_number(low)}")
    elif high is not None:
        parts.append(f"price ≤ {_number(high)}")
    return parts


def create_router(
    admin_chat_id: int,
    sources: list[SourceConfig],
    storage: Storage,
    monitor_enabled: asyncio.Event,
) -> Router:
    router = Router()
    router.message.filter(F.chat.id == admin_chat_id)

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(
            "👋 <b>Website Monitor Bot</b>\n"
            f"Watching {len(sources)} sources for new listings and price drops.\n\n"
            "/status — last check, items found, errors\n"
            "/sources — active sources and filters\n"
            "/pause, /resume — stop or restart monitoring",
            parse_mode="HTML",
        )

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        states = {row["source"]: row for row in await storage.get_status()}
        lines = ["<b>Monitor status</b>"]
        for source in sources:
            state = states.get(source.name, {})
            last_checked = format_checked(state.get("last_checked"))
            errors = state.get("consecutive_failures", 0)
            error_text = state.get("last_error")
            icon = "🔴" if errors else "🟢"
            line = (
                f"{icon} <b>{html.escape(source.name)}</b>\n"
                f"   last check: {html.escape(str(last_checked))}\n"
                f"   items: {state.get('item_count', 0)}; failures in a row: {errors}"
            )
            if error_text:
                line += f"\n   last error: {html.escape(str(error_text)[:300])}"
            lines.append(line)
        lines.append(
            f"Monitoring: {'running' if monitor_enabled.is_set() else 'paused'}"
        )
        await message.answer("\n".join(lines), parse_mode="HTML")

    @router.message(Command("pause"))
    async def pause(message: Message) -> None:
        monitor_enabled.clear()
        await message.answer("Monitoring paused.")

    @router.message(Command("resume"))
    async def resume(message: Message) -> None:
        monitor_enabled.set()
        await message.answer("Monitoring resumed.")

    @router.message(Command("sources"))
    async def list_sources(message: Message) -> None:
        lines = ["<b>Configured sources</b>"]
        for source in sources:
            details = [
                f"every {source.interval_minutes} min",
                source.type.upper() + (" via browser" if source.use_browser else ""),
                *describe_filters(source.filters),
            ]
            lines.append(
                f"• <b>{html.escape(source.name)}</b> — "
                f"{html.escape('; '.join(details))}"
            )
        await message.answer("\n".join(lines), parse_mode="HTML")

    return router
