# Telegram Status Tracker

A lightweight Python tool that tracks a Telegram user's online/offline status using a **hybrid approach**:

- **Primary**: Real-time `UpdateUserStatus` listener (instant reaction, no polling spam)
- **Fallback**: Periodic polling every 5–10 minutes (catches events missed during restarts or disconnects)

All events are stored in a local SQLite database with deduplication, so listener and polling never create duplicate records.

---

## Features

- Real-time status tracking via Telegram MTProto updates
- Automatic deduplication (listener + polling share the same DB)
- Graceful shutdown on `SIGINT` / `SIGTERM`
- SQLite storage with indexed queries
- Environment-based configuration (no hardcoded secrets)
- FloodWait handling (auto-backoff if Telegram rate-limits you)

---

## Requirements

- Python 3.10+
- Telegram API credentials ([my.telegram.org/apps](https://my.telegram.org/apps))
- A Telegram account (phone number)

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/telegram-status-tracker.git
cd telegram-status-tracker

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy example env and fill in your data
cp .env.example .env
nano .env   # or vim, or any editor
```

### `.env` variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TG_API_ID` | Your Telegram API ID (integer) | `12345678` |
| `TG_API_HASH` | Your Telegram API hash | `abcdef1234567890abcdef1234567890` |
| `TG_PHONE` | Your phone number with country code | `+359000000000` |
| `TG_TARGET` | Who to track: phone, @username, or numeric ID | `+359895779209` |
| `TG_DB` | SQLite database filename | `status_events.db` |
| `TG_POLL_INTERVAL` | Fallback poll interval in seconds | `300` |
| `TG_TZ` | Timezone for timestamps | `Europe/Sofia` |

---

## Usage

```bash
python3 tracker.py
```

On first run, Telegram will send you a login code (or ask for 2FA password). A session file (`status_tracker_session.session`) will be created — do not share it.

The tracker will:
1. Log the initial status (`source=init`)
2. Listen for live updates (`source=listener`)
3. Poll periodically as fallback (`source=poll`)

---

## Viewing the data

```bash
# Using sqlite3 CLI
sqlite3 status_events.db "SELECT * FROM status_events ORDER BY id DESC LIMIT 20;"

# Or open with DB Browser for SQLite, DBeaver, etc.
```

### Useful queries

```sql
-- All online events
SELECT * FROM status_events WHERE status_type = 'online' ORDER BY timestamp;

-- Daily online time estimate
SELECT DATE(timestamp), COUNT(*) * 5 / 60.0 AS approx_hours
FROM status_events
WHERE status_type = 'online'
GROUP BY DATE(timestamp);

-- Events from a specific source
SELECT * FROM status_events WHERE source = 'listener' ORDER BY id DESC;
```

---

## Important notes

- **Privacy**: Only track people you know and have consent from. Telegram's Terms of Service apply.
- **FloodWait**: If you get rate-limited, the script auto-sleeps and retries. Do not set `TG_POLL_INTERVAL` below 60 seconds.
- **Target visibility**: If the target has hidden their "Last Seen" from you, you will only receive `hidden` status events.
- **Session file**: Keep `*.session` files secret — they contain your Telegram login.

---

## Project structure

```
telegram-status-tracker/
├── .env.example          # Example configuration
├── .gitignore            # Ignores .env, *.session, *.db
├── config.py             # Config loader
├── requirements.txt      # Python dependencies
├── tracker.py            # Main application
├── utils.py              # DB helpers
└── README.md             # This file
```

---

## License

MIT
