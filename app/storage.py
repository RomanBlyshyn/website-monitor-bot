import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import aiosqlite

from app.models import Item, PriceDrop


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: str) -> None:
        self.path = path
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    price TEXT,
                    currency TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL,
                    image TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    last_price TEXT,
                    PRIMARY KEY (id, source)
                );
                CREATE TABLE IF NOT EXISTS source_state (
                    source TEXT PRIMARY KEY,
                    baseline_complete INTEGER NOT NULL DEFAULT 0,
                    last_checked TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    failure_notified INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                );
                """
            )
            await db.commit()

    async def register_sources(self, source_names: list[str]) -> None:
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.executemany(
                    "INSERT OR IGNORE INTO source_state (source) VALUES (?)",
                    [(name,) for name in source_names],
                )
                await db.commit()

    async def process_items(
        self, source_name: str, items: list[Item]
    ) -> tuple[list[Item], list[PriceDrop], bool]:
        new_items: list[Item] = []
        price_drops: list[PriceDrop] = []

        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("BEGIN IMMEDIATE")
                cursor = await db.execute(
                    "SELECT baseline_complete FROM source_state WHERE source = ?",
                    (source_name,),
                )
                state = await cursor.fetchone()
                if state is None:
                    await db.execute(
                        "INSERT INTO source_state (source) VALUES (?)", (source_name,)
                    )
                    baseline = True
                else:
                    baseline = not bool(state["baseline_complete"])

                now = _now()
                for item in items:
                    cursor = await db.execute(
                        "SELECT last_price FROM items WHERE id = ? AND source = ?",
                        (item.id, source_name),
                    )
                    existing = await cursor.fetchone()
                    price_text = str(item.price) if item.price is not None else None
                    if existing is None:
                        await db.execute(
                            """
                            INSERT INTO items (
                                id, source, title, price, currency, url, image,
                                first_seen, last_seen, last_price
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                item.id,
                                source_name,
                                item.title,
                                price_text,
                                item.currency,
                                item.url,
                                item.image,
                                now,
                                now,
                                price_text,
                            ),
                        )
                        if not baseline:
                            new_items.append(item)
                        continue

                    old_price_text = existing["last_price"]
                    await db.execute(
                        """
                        UPDATE items
                        SET title = ?, price = ?, currency = ?, url = ?, image = ?,
                            last_seen = ?, last_price = COALESCE(?, last_price)
                        WHERE id = ? AND source = ?
                        """,
                        (
                            item.title,
                            price_text,
                            item.currency,
                            item.url,
                            item.image,
                            now,
                            price_text,
                            item.id,
                            source_name,
                        ),
                    )
                    if old_price_text is not None and item.price is not None:
                        old_price = Decimal(old_price_text)
                        if item.price < old_price:
                            price_drops.append(
                                PriceDrop(item, old_price=old_price, new_price=item.price)
                            )

                if baseline:
                    await db.execute(
                        """
                        UPDATE source_state
                        SET baseline_complete = 1
                        WHERE source = ?
                        """,
                        (source_name,),
                    )
                await db.commit()
        return new_items, price_drops, baseline

    async def record_success(self, source_name: str) -> bool:
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                cursor = await db.execute(
                    """
                    SELECT consecutive_failures, failure_notified
                    FROM source_state WHERE source = ?
                    """,
                    (source_name,),
                )
                state = await cursor.fetchone()
                recovered = bool(
                    state
                    and state[0] > 0
                    and state[1]
                )
                await db.execute(
                    """
                    UPDATE source_state
                    SET last_checked = ?, consecutive_failures = 0,
                        failure_notified = 0, last_error = NULL
                    WHERE source = ?
                    """,
                    (_now(), source_name),
                )
                await db.commit()
        return recovered

    async def record_failure(self, source_name: str, error: str) -> tuple[int, bool]:
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO source_state (source) VALUES (?)",
                    (source_name,),
                )
                cursor = await db.execute(
                    """
                    SELECT consecutive_failures, failure_notified
                    FROM source_state WHERE source = ?
                    """,
                    (source_name,),
                )
                state = await cursor.fetchone()
                failures = state[0] + 1
                notified = bool(state[1])
                should_notify = failures >= 3 and not notified
                await db.execute(
                    """
                    UPDATE source_state
                    SET last_checked = ?, consecutive_failures = ?,
                        failure_notified = ?, last_error = ?
                    WHERE source = ?
                    """,
                    (
                        _now(),
                        failures,
                        int(notified or should_notify),
                        error[:1000],
                        source_name,
                    ),
                )
                await db.commit()
        return failures, should_notify

    async def get_status(self) -> list[dict[str, object]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT state.source, state.last_checked, state.consecutive_failures,
                       state.last_error, COUNT(items.id) AS item_count
                FROM source_state AS state
                LEFT JOIN items ON items.source = state.source
                GROUP BY state.source
                ORDER BY state.source
                """
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]
