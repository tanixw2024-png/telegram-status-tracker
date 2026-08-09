"""Utility functions for Telegram Status Tracker."""
import logging
from datetime import datetime

import aiosqlite
import pytz

from config import DB_FILE, TZ

logger = logging.getLogger("status_tracker")


async def init_db() -> None:
    """Initialize SQLite database with required tables and indexes."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                first_name TEXT,
                last_name TEXT,
                status_type TEXT NOT NULL,
                was_online TEXT,
                source TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_time
            ON status_events(user_id, timestamp)
            """
        )
        await db.commit()


async def get_last_type(db: aiosqlite.Connection, user_id: int) -> str | None:
    """Return the last recorded status_type for a given user."""
    async with db.execute(
        "SELECT status_type FROM status_events WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None


async def log_status(
    db: aiosqlite.Connection,
    user,
    status_type: str,
    was_online: str | None = None,
    source: str = "unknown",
) -> bool:
    """
    Log a status change if it differs from the last known status.
    Returns True if a new record was written, False if it was a duplicate.
    """
    last = await get_last_type(db, user.id)
    if last == status_type:
        return False

    tz = pytz.timezone(TZ)
    ts = datetime.now(tz).isoformat()

    await db.execute(
        """
        INSERT INTO status_events
        (timestamp, user_id, first_name, last_name, status_type, was_online, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            user.id,
            user.first_name,
            user.last_name or "",
            status_type,
            was_online,
            source,
        ),
    )
    await db.commit()

    name = f"{user.first_name} {user.last_name or ''}".strip()
    extra = f" (last_seen={was_online})" if was_online else ""
    logger.info(f"[{source:8s}] {name} ({user.id}): {status_type}{extra}")
    return True
