Telegram Status Tracker
A lightweight, professional Python tool that tracks Telegram users' online/offline status using a hybrid approach:
Primary: Real-time UpdateUserStatus listener (instant reaction, filtered at the MTProto level)
Fallback: Periodic polling every 5–10 minutes (round-robin, catches events missed during restarts or disconnects)
Supports up to 10 targets comfortably out of the box.
All events are stored in a local SQLite database with deduplication, WAL mode and proper indexing.
Features
Multi-target — track several users simultaneously via comma-separated TG_TARGETS
Efficient listener — events.Raw is filtered by UpdateUserStatus at the MTProto layer; no get_entity() in the hot path
Smart deduplication — listener and polling share the same deduplication logic
Graceful shutdown — handles SIGINT / SIGTERM cleanly
SQLite with WAL — fast concurrent reads/writes, safe on HDDs
FloodWait handling — auto-backoff with interruptible sleep
Environment-based configuration — no hardcoded secrets
CSV migration tool — migrate_csv_to_sqlite.py for importing legacy data
Requirements
Python 3.10+
Telegram API credentials (my.telegram.org/apps)
A Telegram account (phone number)
Installation
bash
# 1. Clone the repo
git clone https://github.com/tanixw2024-png/telegram-status-tracker.git
cd telegram-status-tracker

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy example env and fill in your data
cp .env.example .env
nano .env
.env variables
Table
Variable	Description	Example
TG_API_ID	Your Telegram API ID (integer)	12345678
TG_API_HASH	Your Telegram API hash	abcdef1234567890abcdef1234567890
TG_PHONE	Your phone number with country code	+359000000000
TG_TARGETS	Comma-separated list: phone, @username or numeric ID	+359895779209,@user,123456789
TG_DB	SQLite database filename	status_events.db
TG_POLL_INTERVAL	Fallback poll interval in seconds (≥60)	300
TG_TZ	Timezone for timestamps	Europe/Sofia
Usage
bash
python3 tracker.py
On first run, Telegram will send you a login code (or ask for 2FA password). A session file (status_tracker_session.session) will be created — do not share it.
The tracker will:
Resolve every target and cache its ID/name
Log the initial status (source=init)
Listen for live updates (source=listener)
Poll periodically as fallback (source=poll)
Press Ctrl+C for graceful shutdown.
Migrating from CSV
If you have an old CSV export and want to merge it into the SQLite database:
bash
# Dry-run first (no changes written)
python3 migrate_csv_to_sqlite.py history.csv status_events.db --dry-run

# Actually migrate
python3 migrate_csv_to_sqlite.py history.csv status_events.db
The script auto-detects common column name variants and skips exact duplicates.
Viewing the data
bash
# Using sqlite3 CLI
sqlite3 status_events.db "SELECT * FROM status_events ORDER BY id DESC LIMIT 20;"
Useful queries
sql
-- All online events for a specific user
SELECT * FROM status_events
WHERE user_id = 123456789 AND status_type = 'online'
ORDER BY timestamp;

-- Daily online time estimate (5 min granularity assumption)
SELECT DATE(timestamp) AS day,
       COUNT(*) * 5 / 60.0 AS approx_hours
FROM status_events
WHERE status_type = 'online'
GROUP BY day;

-- Events from a specific source
SELECT * FROM status_events WHERE source = 'listener' ORDER BY id DESC;
Project structure
plain
telegram-status-tracker/
├── .env.example              # Example configuration
├── .gitignore                # Ignores .env, *.session, *.db
├── config.py                 # Config loader with safe int parsing
├── migrate_csv_to_sqlite.py  # CSV → SQLite migration tool
├── requirements.txt          # Python dependencies
├── tracker.py                # Main application
├── utils.py                  # DB helpers
└── README.md                 # This file
Important notes
Privacy: Only track people you know and have consent from. Telegram's Terms of Service apply.
FloodWait: If you get rate-limited, the script auto-sleeps and retries. Do not set TG_POLL_INTERVAL below 60 seconds.
Target visibility: If a target has hidden their "Last Seen" from you, you will only receive recently, last_week, last_month or hidden events.
Session file: Keep *.session files secret — they contain your Telegram login.
License
MIT
