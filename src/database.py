"""SQLite database operations for the show cache."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .models import ProcessingStatus, Show

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA = """
-- Shows table
CREATE TABLE IF NOT EXISTS shows (
    tvmaze_id INTEGER PRIMARY KEY,
    tvdb_id INTEGER,
    imdb_id TEXT,
    title TEXT NOT NULL,
    language TEXT,
    country TEXT,
    type TEXT,
    status TEXT,
    premiered DATE,
    ended DATE,
    network TEXT,
    web_channel TEXT,
    genres TEXT,
    runtime INTEGER,
    processing_status TEXT NOT NULL DEFAULT 'pending',
    filter_reason TEXT,
    sonarr_series_id INTEGER,
    added_to_sonarr_at DATETIME,
    last_checked DATETIME NOT NULL,
    tvmaze_updated_at INTEGER,
    retry_after DATETIME,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_processing_status ON shows(processing_status);
CREATE INDEX IF NOT EXISTS idx_tvdb_id ON shows(tvdb_id);
CREATE INDEX IF NOT EXISTS idx_language ON shows(language);
CREATE INDEX IF NOT EXISTS idx_country ON shows(country);
CREATE INDEX IF NOT EXISTS idx_type ON shows(type);
CREATE INDEX IF NOT EXISTS idx_premiered ON shows(premiered);
CREATE INDEX IF NOT EXISTS idx_retry_after ON shows(retry_after);
CREATE INDEX IF NOT EXISTS idx_tvmaze_updated_at ON shows(tvmaze_updated_at);

-- Update trigger
CREATE TRIGGER IF NOT EXISTS update_timestamp
AFTER UPDATE ON shows
BEGIN
    UPDATE shows SET updated_at = CURRENT_TIMESTAMP
    WHERE tvmaze_id = NEW.tvmaze_id;
END;

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize database schema."""
    conn.executescript(SCHEMA)

    # Set schema version
    conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()

    logger.info(f"Database schema initialized (version {SCHEMA_VERSION})")


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version."""
    try:
        cursor = conn.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def migrate_schema(conn: sqlite3.Connection, from_version: int) -> None:
    """Run schema migrations."""
    # Future migrations would go here
    logger.info(f"No migrations needed from version {from_version}")


class Database:
    """SQLite database wrapper for show cache."""

    def __init__(self, path: Path):
        """
        Initialize database connection.

        Creates database file and schema if not exists.
        Enables WAL mode for better concurrency.
        """
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        # Initialize or migrate schema
        current_version = get_schema_version(self.conn)
        if current_version == 0:
            init_schema(self.conn)
        elif current_version < SCHEMA_VERSION:
            migrate_schema(self.conn, current_version)

        logger.info(f"Database initialized at {path}")

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def is_healthy(self) -> bool:
        """Check if database is accessible."""
        try:
            self.conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    # ============ Show CRUD ============

    def upsert_show(self, show: Show) -> None:
        """
        Insert or update a show.

        Uses INSERT OR REPLACE with all fields.
        Automatically updates updated_at timestamp.
        """
        data = show.to_db_dict()

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])

        query = f"INSERT OR REPLACE INTO shows ({columns}) VALUES ({placeholders})"

        self.conn.execute(query, list(data.values()))
        self.conn.commit()

    def get_show(self, tvmaze_id: int) -> Optional[Show]:
        """Get show by TVMaze ID."""
        cursor = self.conn.execute(
            "SELECT * FROM shows WHERE tvmaze_id = ?",
            (tvmaze_id,)
        )
        row = cursor.fetchone()
        return Show.from_db_row(row) if row else None

    def get_show_by_tvdb(self, tvdb_id: int) -> Optional[Show]:
        """Get show by TVDB ID."""
        cursor = self.conn.execute(
            "SELECT * FROM shows WHERE tvdb_id = ?",
            (tvdb_id,)
        )
        row = cursor.fetchone()
        return Show.from_db_row(row) if row else None

    def delete_show(self, tvmaze_id: int) -> bool:
        """Delete show by TVMaze ID. Returns True if deleted."""
        cursor = self.conn.execute(
            "DELETE FROM shows WHERE tvmaze_id = ?",
            (tvmaze_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    # ============ Bulk Operations ============

    def upsert_shows(self, shows: list[Show]) -> int:
        """
        Bulk upsert shows.

        Uses executemany for efficiency.
        Returns count of rows affected.
        """
        if not shows:
            return 0

        # Get column names from first show
        data = shows[0].to_db_dict()
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])

        query = f"INSERT OR REPLACE INTO shows ({columns}) VALUES ({placeholders})"

        # Prepare data for all shows
        rows = [list(show.to_db_dict().values()) for show in shows]

        cursor = self.conn.executemany(query, rows)
        self.conn.commit()

        return cursor.rowcount

    def get_shows_by_status(
        self,
        status: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> list[Show]:
        """Get all shows with given processing status."""
        query = "SELECT * FROM shows WHERE processing_status = ?"
        params = [status]

        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cursor = self.conn.execute(query, params)
        return [Show.from_db_row(row) for row in cursor.fetchall()]

    def get_shows_for_retry(self, now: datetime, max_retries: int) -> list[Show]:
        """
        Get shows ready for retry.

        Returns shows where:
        - processing_status = 'pending_tvdb'
        - retry_after <= now
        - retry_count < max_retries
        """
        query = """
            SELECT * FROM shows
            WHERE processing_status = ?
            AND retry_after <= ?
            AND retry_count < ?
        """
        cursor = self.conn.execute(
            query,
            (ProcessingStatus.PENDING_TVDB, now.isoformat(), max_retries)
        )
        return [Show.from_db_row(row) for row in cursor.fetchall()]

    def get_all_filtered_shows(self) -> Iterator[Show]:
        """
        Iterate all filtered shows.

        Uses server-side cursor for memory efficiency.
        Used for filter re-evaluation.
        """
        cursor = self.conn.execute(
            "SELECT * FROM shows WHERE processing_status = ?",
            (ProcessingStatus.FILTERED,)
        )

        while True:
            row = cursor.fetchone()
            if row is None:
                break
            yield Show.from_db_row(row)

    # ============ Statistics ============

    def get_status_counts(self) -> dict[str, int]:
        """
        Get count of shows by processing status.

        Returns: {"added": 1203, "filtered": 67102, ...}
        """
        cursor = self.conn.execute(
            "SELECT processing_status, COUNT(*) as count FROM shows GROUP BY processing_status"
        )
        return {row["processing_status"]: row["count"] for row in cursor.fetchall()}

    def get_filter_reason_counts(self) -> dict[str, int]:
        """
        Get count of filtered shows by reason.

        Returns: {"genre": 23451, "language": 31204, ...}
        """
        cursor = self.conn.execute("""
            SELECT filter_reason, COUNT(*) as count
            FROM shows
            WHERE processing_status = ?
            AND filter_reason IS NOT NULL
            GROUP BY filter_reason
        """, (ProcessingStatus.FILTERED,))

        return {row["filter_reason"]: row["count"] for row in cursor.fetchall()}

    def get_highest_tvmaze_id(self) -> int:
        """Get highest TVMaze ID in database."""
        cursor = self.conn.execute("SELECT MAX(tvmaze_id) as max_id FROM shows")
        row = cursor.fetchone()
        return row["max_id"] or 0

    def get_total_count(self) -> int:
        """Get total show count."""
        cursor = self.conn.execute("SELECT COUNT(*) as count FROM shows")
        row = cursor.fetchone()
        return row["count"] or 0

    def get_retry_counts(self) -> dict[str, int]:
        """Get count of shows pending retry by reason."""
        cursor = self.conn.execute("""
            SELECT error_message, COUNT(*) as count
            FROM shows
            WHERE processing_status = ?
            AND retry_after IS NOT NULL
            GROUP BY error_message
        """, (ProcessingStatus.PENDING_TVDB,))

        return {row["error_message"] or "No TVDB ID": row["count"] for row in cursor.fetchall()}

    # ============ Sync Helpers ============

    def get_tvmaze_ids_updated_since(self, timestamp: int) -> set[int]:
        """Get TVMaze IDs with tvmaze_updated_at >= timestamp."""
        cursor = self.conn.execute(
            "SELECT tvmaze_id FROM shows WHERE tvmaze_updated_at >= ?",
            (timestamp,)
        )
        return {row["tvmaze_id"] for row in cursor.fetchall()}

    def mark_show_added(
        self,
        tvmaze_id: int,
        sonarr_series_id: int
    ) -> None:
        """Mark show as added to Sonarr."""
        self.conn.execute("""
            UPDATE shows SET
                processing_status = ?,
                sonarr_series_id = ?,
                added_to_sonarr_at = ?,
                filter_reason = NULL,
                error_message = NULL
            WHERE tvmaze_id = ?
        """, (
            ProcessingStatus.ADDED,
            sonarr_series_id,
            datetime.utcnow().isoformat(),
            tvmaze_id
        ))
        self.conn.commit()

    def mark_show_filtered(
        self,
        tvmaze_id: int,
        reason: str,
        category: str
    ) -> None:
        """Mark show as filtered with reason."""
        self.conn.execute("""
            UPDATE shows SET
                processing_status = ?,
                filter_reason = ?,
                sonarr_series_id = NULL,
                error_message = NULL
            WHERE tvmaze_id = ?
        """, (ProcessingStatus.FILTERED, f"{category}: {reason}", tvmaze_id))
        self.conn.commit()

    def mark_show_pending_tvdb(
        self,
        tvmaze_id: int,
        retry_after: datetime
    ) -> None:
        """Mark show as pending TVDB ID with retry time."""
        self.conn.execute("""
            UPDATE shows SET
                processing_status = ?,
                retry_after = ?,
                error_message = ?
            WHERE tvmaze_id = ?
        """, (
            ProcessingStatus.PENDING_TVDB,
            retry_after.isoformat(),
            "No TVDB ID available",
            tvmaze_id
        ))
        self.conn.commit()

    def mark_show_failed(
        self,
        tvmaze_id: int,
        error_message: str
    ) -> None:
        """Mark show as permanently failed."""
        self.conn.execute("""
            UPDATE shows SET
                processing_status = ?,
                error_message = ?
            WHERE tvmaze_id = ?
        """, (ProcessingStatus.FAILED, error_message, tvmaze_id))
        self.conn.commit()

    def update_show_status(self, tvmaze_id: int, status: str) -> None:
        """Update show processing status."""
        self.conn.execute(
            "UPDATE shows SET processing_status = ? WHERE tvmaze_id = ?",
            (status, tvmaze_id)
        )
        self.conn.commit()

    def increment_retry_count(self, tvmaze_id: int) -> int:
        """Increment retry count and return new value."""
        cursor = self.conn.execute("""
            UPDATE shows SET retry_count = retry_count + 1
            WHERE tvmaze_id = ?
            RETURNING retry_count
        """, (tvmaze_id,))
        self.conn.commit()

        row = cursor.fetchone()
        return row["retry_count"] if row else 0
