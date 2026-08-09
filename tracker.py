#!/usr/bin/env python3
"""
Telegram Status Tracker — Multi-target edition

Hybrid approach:
  - Primary: Raw UpdateUserStatus listener (real-time, filtered by type)
  - Fallback: Periodic polling (round-robin, catches missed events)

Supports up to 10 targets comfortably.
Configuration is read from environment variables (see .env.example).
"""
import asyncio
import logging
import signal
import sys

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.types import (
    UpdateUserStatus,
    UserStatusEmpty,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)
import aiosqlite

from config import (
    API_HASH,
    API_ID,
    DB_FILE,
    PHONE,
    POLL_INTERVAL,
    TARGETS,
    TZ,
    validate,
)
from utils import init_db, log_status

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("status_tracker")

# Global timezone (import once, use everywhere)
import pytz

tz = pytz.timezone(TZ)


# ---------------------------------------------------------------------------
# Target cache — avoids repeated get_entity() calls in the hot path
# ---------------------------------------------------------------------------
class TargetCache:
    """Lightweight in-memory cache for resolved target entities."""

    def __init__(self):
        self._ids: set[int] = set()
        self._names: dict[int, tuple[str, str]] = {}

    def add(self, entity) -> None:
        self._ids.add(entity.id)
        fn = getattr(entity, "first_name", None) or ""
        ln = getattr(entity, "last_name", None) or ""
        self._names[entity.id] = (fn, ln)

    def __contains__(self, user_id: int) -> bool:
        return user_id in self._ids

    def get_name(self, user_id: int) -> tuple[str, str]:
        return self._names.get(user_id, ("Unknown", ""))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _classify_status(status):
    """Return (status_type, was_online_or_extra)."""
    if isinstance(status, UserStatusOnline):
        extra = status.expires.astimezone(tz).isoformat() if status.expires else None
        return "online", extra
    if isinstance(status, UserStatusOffline):
        was = status.was_online.astimezone(tz).isoformat() if status.was_online else None
        return "offline", was
    if isinstance(status, UserStatusRecently):
        return "recently", None
    if isinstance(status, UserStatusLastWeek):
        return "last_week", None
    if isinstance(status, UserStatusLastMonth):
        return "last_month", None
    if isinstance(status, UserStatusEmpty):
        return "empty", None
    return "hidden", None


async def _resolve_targets(client: TelegramClient) -> tuple[TargetCache, list[str]]:
    """Resolve every target string to a Telegram entity."""
    cache = TargetCache()
    failed: list[str] = []

    for target in TARGETS:
        try:
            entity = await client.get_entity(target)
            cache.add(entity)
            logger.info(f"Resolved target: {entity.first_name} ({entity.id})")
        except Exception as exc:
            logger.error(f"Failed to resolve target '{target}': {exc}")
            failed.append(target)

    return cache, failed


async def _snapshot_all(client: TelegramClient, cache: TargetCache, db: aiosqlite.Connection):
    """Record the initial status for every resolved target."""
    for target in TARGETS:
        try:
            user = await client.get_entity(target)
            stype, extra = _classify_status(user.status)
            fn, ln = cache.get_name(user.id)
            await log_status(db, user.id, fn, ln, stype, extra, source="init")
        except Exception as exc:
            logger.warning(f"Initial snapshot failed for '{target}': {exc}")


# ---------------------------------------------------------------------------
# Listener
# ---------------------------------------------------------------------------
def build_listener(cache: TargetCache, db: aiosqlite.Connection):
    """Build a raw update handler filtered for our target users."""

    async def handler(event):
        # Safety net — Telethon already filters by type, but we keep this
        if not isinstance(event, UpdateUserStatus):
            return
        if event.user_id not in cache:
            return

        stype, extra = _classify_status(event.status)
        fn, ln = cache.get_name(event.user_id)
        await log_status(db, event.user_id, fn, ln, stype, extra, source="listener")

    return handler


# ---------------------------------------------------------------------------
# Fallback polling
# ---------------------------------------------------------------------------
async def polling_task(
    client: TelegramClient,
    cache: TargetCache,
    db: aiosqlite.Connection,
    stop_event: asyncio.Event,
):
    """Background task that periodically polls every target."""
    while not stop_event.is_set():
        try:
            for target in TARGETS:
                if stop_event.is_set():
                    break
                try:
                    user = await client.get_entity(target)
                except FloodWaitError as fwe:
                    logger.warning(f"[poll] FloodWait — sleeping {fwe.seconds}s...")
                    # Respect FloodWait but also check stop_event every second
                    for _ in range(fwe.seconds):
                        if stop_event.is_set():
                            break
                        await asyncio.sleep(1)
                    continue

                stype, extra = _classify_status(user.status)
                fn, ln = cache.get_name(user.id)
                await log_status(db, user.id, fn, ln, stype, extra, source="poll")
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"[poll] Error: {exc}")

        # Sleep while remaining responsive to shutdown
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass

    logger.info("[poll] Task exiting.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    missing = validate()
    if missing:
        logger.error(f"Missing or invalid config: {', '.join(missing)}")
        logger.error("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    await init_db()

    client = TelegramClient("status_tracker_session", API_ID, API_HASH)
    await client.start(PHONE)

    # Resolve all targets up-front
    cache, failed = await _resolve_targets(client)
    if not cache._ids:
        logger.error("No targets could be resolved. Exiting.")
        await client.disconnect()
        sys.exit(1)
    if failed:
        logger.warning(f"Unresolved targets (will retry via polling): {failed}")

    db = await aiosqlite.connect(DB_FILE)

    # Initial snapshot so we know the starting state
    await _snapshot_all(client, cache, db)

    # Register listener — filtered at the MTProto level so we only receive
    # UpdateUserStatus updates, not every raw packet.
    listener = build_listener(cache, db)
    client.add_event_handler(listener, events.Raw(types=UpdateUserStatus))

    # Graceful shutdown machinery
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _shutdown():
        logger.info("Shutdown signal received...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    # Start fallback polling
    poll_task = asyncio.create_task(
        polling_task(client, cache, db, stop_event),
        name="poll_fallback",
    )

    logger.info(
        f"Tracker started. Listening for live updates + polling every {POLL_INTERVAL}s. "
        f"Targets: {len(cache._ids)}. Press Ctrl+C to stop."
    )

    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass

    client.remove_event_handler(listener, events.Raw(types=UpdateUserStatus))
    await db.close()
    await client.disconnect()
    logger.info("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
