import json
import os
import pathlib
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "/data/brackets.db")
MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def _run_migrations(con: sqlite3.Connection):
    con.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    applied = {row[0] for row in con.execute("SELECT filename FROM schema_migrations").fetchall()}

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        print(f"Running migration: {path.name}")
        con.executescript(path.read_text())
        con.execute(
            "INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?)",
            (path.name, datetime.now(timezone.utc).isoformat()),
        )
        con.commit()


def init_db():
    with sqlite3.connect(DB_PATH) as con:
        # Base schema (original v1 tables)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS brackets (
                discord_user_id INTEGER PRIMARY KEY,
                display_name    TEXT NOT NULL,
                picks_json      TEXT NOT NULL,
                submitted_at    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS digest_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id        INTEGER PRIMARY KEY,
                taunt_channel_id INTEGER NOT NULL
            );
        """)
        _run_migrations(con)


def upsert_bracket(discord_user_id: int, guild_id: int, display_name: str, picks: dict):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            INSERT INTO brackets (discord_user_id, guild_id, display_name, picks_json, submitted_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(discord_user_id, guild_id) DO UPDATE SET
                display_name = excluded.display_name,
                picks_json   = excluded.picks_json,
                submitted_at = excluded.submitted_at
            """,
            (
                discord_user_id,
                guild_id,
                display_name,
                json.dumps(picks),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def get_bracket(discord_user_id: int, guild_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT picks_json FROM brackets WHERE discord_user_id = ? AND guild_id = ?",
            (discord_user_id, guild_id),
        ).fetchone()
    return json.loads(row[0]) if row else None


def get_guild_brackets(guild_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT discord_user_id, display_name, picks_json FROM brackets WHERE guild_id = ?",
            (guild_id,),
        ).fetchall()
    return [
        {"discord_user_id": r[0], "display_name": r[1], "picks": json.loads(r[2])}
        for r in rows
    ]


def get_digest_state(key: str) -> str | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT value FROM digest_state WHERE key = ?", (key,)
        ).fetchone()
    return row[0] if row else None


def set_guild_channel(guild_id: int, channel_id: int):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO guild_settings (guild_id, taunt_channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET taunt_channel_id = excluded.taunt_channel_id",
            (guild_id, channel_id),
        )


def get_all_guild_channels() -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT guild_id, taunt_channel_id FROM guild_settings"
        ).fetchall()
    return [{"guild_id": r[0], "channel_id": r[1]} for r in rows]


def set_digest_state(key: str, value: str):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO digest_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
