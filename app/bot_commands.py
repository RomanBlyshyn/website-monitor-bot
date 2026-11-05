import html
import logging
import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import SourceConfig
from app.storage import Storage

logger = logging.getLogger(__name__)


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
            last_checked = state.get("last_checked") or "not checked yet"
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
            filters = source.filters
            details = [
                f"interval: {source.interval_minutes} min",
                f"type: {source.type}",
            ]
            if filters.include_keywords:
                details.append(
                    "include: " + ", ".join(filters.include_keywords)
                )
            if filters.exclude_keywords:
                details.append("exclude: " + ", ".join(filters.exclude_keywords))
            if filters.min_price is not None:
                details.append(f"min: {filters.min_price}")
            if filters.max_price is not None:
                details.append(f"max: {filters.max_price}")
            lines.append(
                f"• <b>{html.escape(source.name)}</b> — "
                f"{html.escape('; '.join(details))}"
            )
        await message.answer("\n".join(lines), parse_mode="HTML")

    return router
