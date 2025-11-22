"""Helpers for recording scraper heartbeat timestamps."""

import os
from contextlib import closing
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

_TABLE_INITIALIZED = False


def _get_connection():
    """Create a short-lived PostgreSQL connection."""
    load_dotenv(override=False)
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '54594'),
        database=os.getenv('DB_NAME', 'pjx'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres'),
        connect_timeout=5
    )


def _ensure_table(cursor):
    """Create the heartbeats table once per process."""
    global _TABLE_INITIALIZED
    if _TABLE_INITIALIZED:
        return

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraper_heartbeats (
            scraper_name VARCHAR(100) PRIMARY KEY,
            last_run TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _TABLE_INITIALIZED = True


def touch_heartbeat(scraper_name: str):
    """Record the most recent run time of a scraper."""
    if not scraper_name:
        return

    try:
        with closing(_get_connection()) as conn:
            with conn.cursor() as cursor:
                _ensure_table(cursor)
                cursor.execute(
                    """
                    INSERT INTO scraper_heartbeats (scraper_name, last_run)
                    VALUES (%s, %s)
                    ON CONFLICT (scraper_name)
                    DO UPDATE SET last_run = EXCLUDED.last_run
                    """,
                    (scraper_name, datetime.utcnow())
                )
            conn.commit()
    except Exception:
        # Heartbeat failures should not crash scrapers; log silently.
        pass
