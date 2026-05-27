"""
database.py — Privacy-first schema for Lost & Found AI Platform
New tables: match_sessions (private pairing), recovery_confirmations
Removed: public recommendation data
"""
import os, sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "campus.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT UNIQUE NOT NULL,
        password        TEXT NOT NULL,
        role            TEXT DEFAULT 'user',
        stars           INTEGER DEFAULT 0,
        credits         INTEGER DEFAULT 100,
        level           TEXT DEFAULT 'Newcomer',
        badge           TEXT DEFAULT '🌱',
        banned          INTEGER DEFAULT 0,
        recoveries      INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS reports (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT NOT NULL,
        type            TEXT NOT NULL,
        item            TEXT NOT NULL,
        description     TEXT,
        place           TEXT,
        date            TEXT,
        contact         TEXT,
        image           TEXT,
        status          TEXT DEFAULT 'active',
        resolved_by     TEXT,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (username) REFERENCES users(username)
    );

    /* Private match session — only the two matched users can see details */
    CREATE TABLE IF NOT EXISTS match_sessions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        report_lost     INTEGER NOT NULL,
        report_found    INTEGER NOT NULL,
        user_lost       TEXT NOT NULL,
        user_found      TEXT NOT NULL,
        score           REAL NOT NULL,
        status          TEXT DEFAULT 'pending',
        confirmed_by_lost  INTEGER DEFAULT 0,
        confirmed_by_found INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (report_lost)  REFERENCES reports(id),
        FOREIGN KEY (report_found) REFERENCES reports(id)
    );

    /* Messages are scoped to a match_session — no free-DM spam */
    CREATE TABLE IF NOT EXISTS messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      INTEGER,
        sender          TEXT NOT NULL,
        receiver        TEXT NOT NULL,
        body            TEXT NOT NULL,
        read            INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES match_sessions(id)
    );

    CREATE TABLE IF NOT EXISTS chat_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT NOT NULL,
        role            TEXT NOT NULL,
        message         TEXT NOT NULL,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT NOT NULL,
        text            TEXT NOT NULL,
        link            TEXT,
        read            INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS activity_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT,
        action          TEXT NOT NULL,
        detail          TEXT,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Safe migrations for existing databases
    migrations = [
        ("users",    "role",         "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'"),
        ("users",    "level",        "ALTER TABLE users ADD COLUMN level TEXT DEFAULT 'Newcomer'"),
        ("users",    "badge",        "ALTER TABLE users ADD COLUMN badge TEXT DEFAULT '\U0001f331'"),
        ("users",    "banned",       "ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0"),
        ("users",    "recoveries",   "ALTER TABLE users ADD COLUMN recoveries INTEGER DEFAULT 0"),
        ("reports",  "resolved_by",  "ALTER TABLE reports ADD COLUMN resolved_by TEXT"),
        ("messages", "session_id",   "ALTER TABLE messages ADD COLUMN session_id INTEGER"),
    ]
    for table, col, sql in migrations:
        try:
            c.execute(f"SELECT {col} FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            try: c.execute(sql)
            except: pass

    conn.commit()
    conn.close()
    print("[DB] Schema ready.")

# ── Helpers ──────────────────────────────────────────────────────────────────

def log_activity(username, action, detail=""):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO activity_log (username, action, detail) VALUES (?,?,?)",
            (username, action, detail)
        )
        conn.commit()
        conn.close()
    except: pass

def push_notification(username, text, link=""):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO notifications (username, text, link) VALUES (?,?,?)",
            (username, text, link)
        )
        conn.commit()
        conn.close()
    except: pass

LEVEL_MAP = [
    (0,   "Newcomer",  "🌱"),
    (3,   "Helper",    "🤝"),
    (8,   "Trusted",   "⭐"),
    (20,  "Champion",  "🏆"),
    (50,  "Legend",    "🌟"),
    (100, "Guardian",  "👑"),
]

def compute_level(stars):
    level, badge = "Newcomer", "🌱"
    for threshold, lv, bd in LEVEL_MAP:
        if stars >= threshold:
            level, badge = lv, bd
    return level, badge

def update_user_level(username):
    conn = get_db()
    row = conn.execute("SELECT stars FROM users WHERE username=?", (username,)).fetchone()
    if row:
        level, badge = compute_level(row["stars"])
        conn.execute("UPDATE users SET level=?, badge=? WHERE username=?",
                     (level, badge, username))
        conn.commit()
    conn.close()

def is_session_participant(session_id, username):
    """Security check: confirm user belongs to this match session."""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM match_sessions WHERE id=? AND (user_lost=? OR user_found=?)",
        (session_id, username, username)
    ).fetchone()
    conn.close()
    return row is not None
