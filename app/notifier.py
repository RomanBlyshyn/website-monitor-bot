import asyncio
import html
import logging
from datetime import datetime
from decimal import Decimal

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Item, Notification, PriceDrop

logger = logging.getLogger(__name__)


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
        title = html.escape(item.title)
        source = html.escape(item.source)
        price = html.escape(str(item.price) if item.price is not None else "Price unknown")
        currency = html.escape(item.currency)
        time_text = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        text = (
            f"🆕 New listing — {source}\n"
            f"<b>{title}</b>\n"
            f"💰 {price} {currency}\n"
            f"🕒 {html.escape(time_text)}"
        )
        await self._queue.put(Notification(text=text, url=item.url, image=item.image))

    async def send_price_drop(self, drop: PriceDrop) -> None:
        item = drop.item
        percent = (
            (drop.old_price - drop.new_price) / drop.old_price * Decimal("100")
        )
        text = (
            f"💸 Price drop — {html.escape(item.source)}\n"
            f"<b>{html.escape(item.title)}</b>\n"
            f"<s>{html.escape(str(drop.old_price))}</s> → "
            f"<b>{html.escape(str(drop.new_price))}</b> "
            f"{html.escape(item.currency)} (-{percent:.1f}%)"
        )
        await self._queue.put(Notification(text=text, url=item.url))

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
                await asyncio.sleep(1.05)
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

        for attempt in range(3):
            try:
                if notification.image:
                    caption = notification.text
                    if len(caption) > 1024:
                        caption = caption[:1021] + "..."
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=notification.image,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=notification.text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                return
            except Exception:
                if attempt == 2:
                    logger.exception("Failed to deliver Telegram notification")
                    return
                await asyncio.sleep(2**attempt)
