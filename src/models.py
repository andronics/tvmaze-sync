"""Data structures and type definitions for TVMaze-Sync."""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from typing import Optional


class ProcessingStatus:
    """Show processing status values."""

    PENDING = "pending"           # New, not yet processed
    FILTERED = "filtered"         # Excluded by filters
    PENDING_TVDB = "pending_tvdb" # No TVDB ID, will retry
    ADDED = "added"               # Successfully added to Sonarr
    EXISTS = "exists"             # Already in Sonarr
    FAILED = "failed"             # Sonarr rejected, permanent
    SKIPPED = "skipped"           # Manually excluded


class Decision(Enum):
    """Processing decision for a show."""

    ADD = "add"
    FILTER = "filter"
    SKIP = "skip"
    RETRY = "retry"


@dataclass
class Show:
    """TV show metadata from TVMaze."""

    tvmaze_id: int
    title: str

    # External IDs
    tvdb_id: Optional[int] = None
    imdb_id: Optional[str] = None

    # Filterable metadata
    language: Optional[str] = None
    country: Optional[str] = None
    type: Optional[str] = None          # Scripted, Reality, Animation, etc.
    status: Optional[str] = None        # Running, Ended, In Development, etc.
    premiered: Optional[date] = None
    ended: Optional[date] = None
    network: Optional[str] = None
    web_channel: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    runtime: Optional[int] = None

    # Processing state
    processing_status: str = ProcessingStatus.PENDING
    filter_reason: Optional[str] = None
    sonarr_series_id: Optional[int] = None
    added_to_sonarr_at: Optional[datetime] = None

    # Sync metadata
    last_checked: datetime = field(default_factory=lambda: datetime.now(UTC))
    tvmaze_updated_at: Optional[int] = None  # Unix timestamp
    retry_after: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None

    @classmethod
    def from_tvmaze_response(cls, data: dict) -> "Show":
        """Parse TVMaze API response into Show object."""
        # Extract external IDs
        externals = data.get("externals", {})
        tvdb_id = externals.get("thetvdb")
        imdb_id = externals.get("imdb")

        # Extract country from network or web channel
        country = None
        network_data = data.get("network")
        web_channel_data = data.get("webChannel")

        if network_data and network_data.get("country"):
            country = network_data["country"].get("code")
        elif web_channel_data and web_channel_data.get("country"):
            country = web_channel_data["country"].get("code")

        # Parse dates
        premiered = None
        if data.get("premiered"):
            try:
                premiered = date.fromisoformat(data["premiered"])
            except (ValueError, TypeError):
                pass

        ended = None
        if data.get("ended"):
            try:
                ended = date.fromisoformat(data["ended"])
            except (ValueError, TypeError):
                pass

        return cls(
            tvmaze_id=data["id"],
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            title=data.get("name", "Unknown"),
            language=data.get("language"),
            country=country,
            type=data.get("type"),
            status=data.get("status"),
            premiered=premiered,
            ended=ended,
            network=network_data.get("name") if network_data else None,
            web_channel=web_channel_data.get("name") if web_channel_data else None,
            genres=data.get("genres", []),
            runtime=data.get("runtime"),
            tvmaze_updated_at=data.get("updated"),
        )

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "Show":
        """Parse SQLite row into Show object."""
        # Parse genres from JSON string
        genres = []
        if row["genres"]:
            try:
                genres = json.loads(row["genres"])
            except json.JSONDecodeError:
                pass

        # Parse dates
        premiered = None
        if row["premiered"]:
            try:
                premiered = date.fromisoformat(row["premiered"])
            except (ValueError, TypeError):
                pass

        ended = None
        if row["ended"]:
            try:
                ended = date.fromisoformat(row["ended"])
            except (ValueError, TypeError):
                pass

        # Parse datetimes
        last_checked = None
        if row["last_checked"]:
            try:
                last_checked = datetime.fromisoformat(row["last_checked"])
            except (ValueError, TypeError):
                pass

        added_to_sonarr_at = None
        if row["added_to_sonarr_at"]:
            try:
                added_to_sonarr_at = datetime.fromisoformat(row["added_to_sonarr_at"])
            except (ValueError, TypeError):
                pass

        retry_after = None
        if row["retry_after"]:
            try:
                retry_after = datetime.fromisoformat(row["retry_after"])
            except (ValueError, TypeError):
                pass

        return cls(
            tvmaze_id=row["tvmaze_id"],
            tvdb_id=row["tvdb_id"],
            imdb_id=row["imdb_id"],
            title=row["title"],
            language=row["language"],
            country=row["country"],
            type=row["type"],
            status=row["status"],
            premiered=premiered,
            ended=ended,
            network=row["network"],
            web_channel=row["web_channel"],
            genres=genres,
            runtime=row["runtime"],
            processing_status=row["processing_status"],
            filter_reason=row["filter_reason"],
            sonarr_series_id=row["sonarr_series_id"],
            added_to_sonarr_at=added_to_sonarr_at,
            last_checked=last_checked,
            tvmaze_updated_at=row["tvmaze_updated_at"],
            retry_after=retry_after,
            retry_count=row["retry_count"] or 0,
            error_message=row["error_message"],
        )

    def to_db_dict(self) -> dict:
        """Convert to dictionary for SQLite insert/update."""
        return {
            "tvmaze_id": self.tvmaze_id,
            "tvdb_id": self.tvdb_id,
            "imdb_id": self.imdb_id,
            "title": self.title,
            "language": self.language,
            "country": self.country,
            "type": self.type,
            "status": self.status,
            "premiered": self.premiered.isoformat() if self.premiered else None,
            "ended": self.ended.isoformat() if self.ended else None,
            "network": self.network,
            "web_channel": self.web_channel,
            "genres": json.dumps(self.genres) if self.genres else None,
            "runtime": self.runtime,
            "processing_status": self.processing_status,
            "filter_reason": self.filter_reason,
            "sonarr_series_id": self.sonarr_series_id,
            "added_to_sonarr_at": self.added_to_sonarr_at.isoformat() if self.added_to_sonarr_at else None,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "tvmaze_updated_at": self.tvmaze_updated_at,
            "retry_after": self.retry_after.isoformat() if self.retry_after else None,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "tvmaze_id": self.tvmaze_id,
            "tvdb_id": self.tvdb_id,
            "imdb_id": self.imdb_id,
            "title": self.title,
            "language": self.language,
            "country": self.country,
            "type": self.type,
            "status": self.status,
            "premiered": self.premiered.isoformat() if self.premiered else None,
            "ended": self.ended.isoformat() if self.ended else None,
            "network": self.network,
            "web_channel": self.web_channel,
            "genres": self.genres,
            "runtime": self.runtime,
            "processing_status": self.processing_status,
            "filter_reason": self.filter_reason,
            "sonarr_series_id": self.sonarr_series_id,
            "added_to_sonarr_at": self.added_to_sonarr_at.isoformat() if self.added_to_sonarr_at else None,
        }


@dataclass
class ProcessingResult:
    """Result of processing a show through filters."""

    decision: Decision
    reason: Optional[str] = None
    filter_category: Optional[str] = None  # genre, language, country, etc.
    sonarr_params: Optional["SonarrParams"] = None


@dataclass
class SonarrParams:
    """Parameters for Sonarr add_series call."""

    tvdb_id: int
    title: str
    root_folder: str
    quality_profile_id: int
    language_profile_id: Optional[int]  # None for Sonarr v4+
    monitor: str
    search_on_add: bool
    tags: list[int] = field(default_factory=list)


@dataclass
class SyncStats:
    """Statistics from a sync cycle."""

    started_at: datetime
    completed_at: Optional[datetime] = None
    shows_processed: int = 0
    shows_added: int = 0
    shows_filtered: int = 0
    shows_skipped: int = 0
    shows_failed: int = 0
    shows_exists: int = 0
    api_calls_tvmaze: int = 0
    api_calls_sonarr: int = 0

    @property
    def duration_seconds(self) -> float:
        """Calculate duration of sync cycle in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
