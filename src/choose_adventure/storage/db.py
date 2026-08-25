import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    premise TEXT NOT NULL,
    tone TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    last_page_id INTEGER
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    seq INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    is_ending INTEGER NOT NULL DEFAULT 0,
    parent_page_id INTEGER REFERENCES pages(id),
    ascii_art TEXT NOT NULL DEFAULT '',
    UNIQUE(story_id, seq)
);

CREATE TABLE IF NOT EXISTS options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES pages(id),
    seq INTEGER NOT NULL,
    label TEXT NOT NULL,
    target_page_id INTEGER REFERENCES pages(id),
    UNIQUE(page_id, seq)
);

CREATE TABLE IF NOT EXISTS character_states (
    page_id INTEGER PRIMARY KEY REFERENCES pages(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    condition TEXT NOT NULL DEFAULT '',
    traits TEXT NOT NULL DEFAULT '[]',
    inventory TEXT NOT NULL DEFAULT '[]'
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Create a new SQLite connection with row_factory and foreign keys."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist, migrate older versions, set schema version."""
    conn.executescript(SCHEMA_SQL)
    # Migrate existing databases: v1 -> v2 adds the ascii_art column to pages.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(pages)")}
    if "ascii_art" not in cols:
        conn.execute("ALTER TABLE pages ADD COLUMN ascii_art TEXT NOT NULL DEFAULT ''")
    # Set/verify schema version
    cursor = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    row = cursor.fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
        )
    else:
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION),)
        )
    conn.commit()
