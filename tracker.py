#!/usr/bin/env python3
"""
Telegram Status Tracker

Hybrid approach:
  - Primary: Raw UpdateUserStatus listener (real-time)
  - Fallback: Periodic polling (catches missed events after restart/disconnect)

Configuration is read from environment variables (see .env.example).
"""
import asyncio
import logging
import signal
import sys

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.types import UpdateUserStatus, UserStatusOnline, UserStatusOffline
import aiosqlite

from config import API_ID, API_HASH, PHONE, TARGET, DB_FILE, POLL_INTERVAL, TZ, validate
from utils import init_db, log_status

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("status_tracker")


# --- Listener handler ---
def build_listener(client: TelegramClient, db: aiosqlite.Connection, target_id: int):
    """Build a raw update handler filtered for the target user."""

    async def handler(event):
        if not isinstance(event, UpdateUserStatus):
            return
        if event.user_id != target_id:
            return

        status = event.status
        if isinstance(status, UserStatusOnline):
            stype, was = "online", None
        elif isinstance(status, UserStatusOffline):
            import pytz
            tz = pytz.timezone(TZ)
            was = status.was_online.astimezone(tz).isoformat() if status.was_online else None
            stype = "offline"
        else:
            stype, was = "hidden", None

        try:
            user = await client.get_entity(event.user_id)
            await log_status(db, user, stype, was, "listener")
        except Exception as e:
            logger.error(f"[listener] Error processing update for {event.user_id}: {e}")

    return handler


# --- Fallback polling task ---
async def polling_task(
    client: TelegramClient,
    db: aiosqlite.Connection,
    target_id: int,
    target_input: str,
):
    """Background task that periodically polls the target status."""
    import pytz
    tz = pytz.timezone(TZ)

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)

            user = await client.get_entity(target_input)
            status = user.status

            if isinstance(status, UserStatusOnline):
                stype, was = "online", None
            elif isinstance(status, UserStatusOffline):
                was = status.was_online.astimezone(tz).isoformat() if status.was_online else None
                stype = "offline"
            else:
                stype, was = "hidden", None

            await log_status(db, user, stype, was, "poll")

        except FloodWaitError as e:
            logger.warning(f"[poll] FloodWait — sleeping {e.seconds}s...")
            await asyncio.sleep(e.seconds)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[poll] Error: {e}")


# --- Main ---
async def main():
    missing = validate()
    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        logger.error("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    await init_db()

    client = TelegramClient("status_tracker_session", API_ID, API_HASH)
    await client.start(PHONE)

    # Resolve target once
    try:
        target_entity = await client.get_entity(TARGET)
        target_id = target_entity.id
        logger.info(f"Target: {target_entity.first_name} ({target_id})")
    except Exception as e:
        logger.error(f"Failed to resolve target '{TARGET}': {e}")
        await client.disconnect()
        sys.exit(1)

    db = await aiosqlite.connect(DB_FILE)

    # Initial snapshot so we know the starting state
    try:
        user = await client.get_entity(TARGET)
        status = user.status
        if isinstance(status, UserStatusOnline):
            stype = "online"
        elif isinstance(status, UserStatusOffline):
            stype = "offline"
        else:
            stype = "hidden"
        await log_status(db, user, stype, source="init")
    except Exception as e:
        logger.warning(f"Initial status check failed: {e}")

    # Register listener
    listener = build_listener(client, db, target_id)
    client.add_event_handler(listener, events.Raw)

    # Start fallback polling
    poll_task = asyncio.create_task(
        polling_task(client, db, target_id, TARGET),
        name="poll_fallback",
    )

    # Graceful shutdown
    stop_event = asyncio.Event()

    def shutdown():
        logger.info("Shutdown signal received...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    logger.info(
        "Tracker started. Listening for live updates + polling every %ds.",
        POLL_INTERVAL,
    )
    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass

    client.remove_event_handler(listener, events.Raw)
    await db.close()
    await client.disconnect()
    logger.info("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
