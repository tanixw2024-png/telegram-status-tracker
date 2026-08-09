"""Configuration loader for Telegram Status Tracker."""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram API
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
PHONE = os.getenv("TG_PHONE", "")

# Target to track
TARGET = os.getenv("TG_TARGET", "")

# Database
DB_FILE = os.getenv("TG_DB", "status_events.db")

# Polling
POLL_INTERVAL = int(os.getenv("TG_POLL_INTERVAL", "300"))

# Timezone
TZ = os.getenv("TG_TZ", "Europe/Sofia")


def validate() -> list[str]:
    """Return list of missing required configuration keys."""
    missing = []
    if not API_ID:
        missing.append("TG_API_ID")
    if not API_HASH:
        missing.append("TG_API_HASH")
    if not PHONE:
        missing.append("TG_PHONE")
    if not TARGET:
        missing.append("TG_TARGET")
    return missing
