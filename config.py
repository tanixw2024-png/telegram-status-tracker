"""Configuration loader for Telegram Status Tracker."""
import os
from dotenv import load_dotenv

load_dotenv()


def _int(var: str, default: int) -> int:
    """Safely read an integer env variable."""
    try:
        return int(os.getenv(var, str(default)))
    except (ValueError, TypeError):
        return default


# Telegram API
API_ID = _int("TG_API_ID", 0)
API_HASH = os.getenv("TG_API_HASH", "")
PHONE = os.getenv("TG_PHONE", "")

# Targets to track (comma-separated, e.g. "+359...,@username,123456789")
TARGETS_RAW = os.getenv("TG_TARGETS", "")
TARGETS = [t.strip() for t in TARGETS_RAW.split(",") if t.strip()]

# Database
DB_FILE = os.getenv("TG_DB", "status_events.db")

# Polling
POLL_INTERVAL = _int("TG_POLL_INTERVAL", 300)

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
    if not TARGETS:
        missing.append("TG_TARGETS")
    if POLL_INTERVAL < 60:
        missing.append("TG_POLL_INTERVAL (must be >= 60)")
    return missing
