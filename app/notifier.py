import asyncio
import html
import logging
from datetime import datetime
from decimal import Decimal

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Item, Notification, PriceDrop

logger = logging.getLogger(__name__)

SEND_INTERVAL_SECONDS = 1.05  # Telegram allows ~1 message/second per chat.


def format_price(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def format_new_listing(item: Item, now: datetime | None = None) -> str:
    now = now or datetime.now().astimezone()
    price = format_price(item.price) if item.price is not None else "Price not listed"
    return (
        f"🆕 New listing — {html.escape(item.source)}\n"
        f"<b>{html.escape(item.title)}</b>\n"
        f"💰 {html.escape(price)} {html.escape(item.currency)}".rstrip()
        + f"\n🕒 {html.escape(now.strftime('%Y-%m-%d %H:%M %Z').strip())}"
    )


def format_price_drop(drop: PriceDrop) -> str:
    item = drop.item
    percent = (drop.old_price - drop.new_price) / drop.old_price * Decimal("100")
    return (
        f"💸 Price drop — {html.escape(item.source)}\n"
        f"<b>{html.escape(item.title)}</b>\n"
        f"<s>{format_price(drop.old_price)}</s> → "
        f"<b>{format_price(drop.new_price)}</b> "
        f"{html.escape(item.currency)} (-{percent:.0f}%)"
    )


class TelegramNotifier:
    def __init__(self, bot: Bot, chat_id: int, admin_chat_id: int) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.admin_chat_id = admin_chat_id
        self._queue: asyncio.Queue[Notification | None] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def close(self) -> None:
        if self._worker is not None:
            await self._queue.put(None)
            await self._worker
            self._worker = None

    async def send_new(self, item: Item) -> None:
        await self._queue.put(
            Notification(text=format_new_listing(item), url=item.url, image=item.image)
        )

    async def send_price_drop(self, drop: PriceDrop) -> None:
        await self._queue.put(
            Notification(text=format_price_drop(drop), url=drop.item.url)
        )

    async def send_admin_message(self, text: str) -> None:
        await self._queue.put(
            Notification(
                text=html.escape(text),
                url="",
                chat_id=self.admin_chat_id,
            )
        )

    async def _run(self) -> None:
        while True:
            notification = await self._queue.get()
            try:
                if notification is None:
                    return
                await self._send_with_retries(notification)
                await asyncio.sleep(SEND_INTERVAL_SECONDS)
            finally:
                self._queue.task_done()

    async def _send_with_retries(self, notification: Notification) -> None:
        keyboard = None
        chat_id = notification.chat_id or self.chat_id
        if notification.url:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Open listing", url=notification.url)]
                ]
            )

        use_photo = bool(notification.image) and len(notification.text) <= 1024
        for attempt in range(3):
            try:
                if use_photo:
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=notification.image,
                        caption=notification.text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=notification.text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
                return
            except TelegramRetryAfter as error:
                logger.warning("Telegram rate limit hit; waiting %ss", error.retry_after)
                await asyncio.sleep(error.retry_after)
            except TelegramBadRequest as error:
                if use_photo:
                    # Telegram could not fetch/accept the image: send text instead.
                    logger.warning("sendPhoto rejected (%s); sending text", error)
                    use_photo = False
                    continue
                logger.error("Telegram rejected notification: %s", error)
                return
            except Exception:
                if attempt == 2:
                    logger.exception("Failed to deliver Telegram notification")
                    return
                await asyncio.sleep(2**attempt)
        logger.error("Gave up delivering Telegram notification to %s", chat_id)
