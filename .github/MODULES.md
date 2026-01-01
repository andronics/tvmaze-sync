# TVMaze-Sync Module Documentation

This document provides detailed specifications for each module in the TVMaze-Sync application.

## Module Overview

```
src/
├── __init__.py
├── main.py              # Application entry point and orchestration
├── config.py            # Configuration loading and validation
├── models.py            # Data structures and type definitions
├── database.py          # SQLite database operations
├── state.py             # JSON state management
├── processor.py         # Show filtering and processing logic
├── scheduler.py         # Sync cycle scheduling
├── server.py            # Flask HTTP server
├── metrics.py           # Prometheus metric definitions
└── clients/
    ├── __init__.py
    ├── tvmaze.py        # TVMaze API client
    └── sonarr.py        # Sonarr API client (pyarr wrapper)
```

---

## models.py

Data structures used throughout the application.

### Show

Represents a TV show with all metadata from TVMaze.

```python
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

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
    rating: Optional[float] = None      # TVMaze rating.average (0-10)

    # Processing state
    processing_status: str = "pending"
    filter_reason: Optional[str] = None
    sonarr_series_id: Optional[int] = None
    added_to_sonarr_at: Optional[datetime] = None

    # Sync metadata
    last_checked: Optional[datetime] = None
    tvmaze_updated_at: Optional[int] = None  # Unix timestamp
    retry_after: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None

    @classmethod
    def from_tvmaze_response(cls, data: dict) -> "Show":
        """Parse TVMaze API response into Show object."""
        ...

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "Show":
        """Parse SQLite row into Show object."""
        ...

    def to_db_dict(self) -> dict:
        """Convert to dictionary for SQLite insert/update."""
        ...
```

### ProcessingStatus

Enumeration of possible show processing states.

```python
class ProcessingStatus:
    """Show processing status values."""
    PENDING = "pending"           # New, not yet processed
    FILTERED = "filtered"         # Excluded by filters
    PENDING_TVDB = "pending_tvdb" # No TVDB ID, will retry
    ADDED = "added"               # Successfully added to Sonarr
    EXISTS = "exists"             # Already in Sonarr
    FAILED = "failed"             # Sonarr rejected, permanent
    SKIPPED = "skipped"           # Manually excluded
```

### ProcessingResult

Result of processing a single show.

```python
from enum import Enum

class Decision(Enum):
    ADD = "add"
    FILTER = "filter"
    SKIP = "skip"
    RETRY = "retry"

@dataclass
class ProcessingResult:
    """Result of processing a show through filters."""
    decision: Decision
    reason: Optional[str] = None
    filter_category: Optional[str] = None  # genre, language, country, etc.
    sonarr_params: Optional[SonarrParams] = None
```

### SonarrParams

Parameters for adding a show to Sonarr.

```python
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
```

### SyncStats

Statistics from a sync cycle.

```python
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
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0
```

---

## config.py

Configuration loading, environment variable resolution, and validation.

### Key Functions

```python
def load_config(path: Path | None = None) -> Config:
    """
    Load configuration from YAML file with environment variable resolution.

    Resolution order:
    1. Load YAML file (default: /config/config.yaml)
    2. Resolve ${VAR} and ${VAR_FILE} placeholders
    3. Apply environment variable overrides
    4. Validate required fields and types
    5. Return frozen Config object

    Raises:
        ConfigurationError: If config is invalid or missing required fields
    """
    ...

def resolve_env_value(value: str) -> str:
    """
    Resolve environment variable placeholders.

    Supports:
    - ${VAR} - Direct environment variable
    - ${VAR_FILE} - Read from file (Docker secrets pattern)

    For ${VAR_FILE}:
    1. Look for VAR_FILE env var containing path
    2. Read and strip file contents
    3. Fall back to VAR if VAR_FILE not set

    Raises:
        ConfigurationError: If variable not found
    """
    ...

def apply_env_overrides(config: dict) -> dict:
    """
    Apply environment variable overrides to config dict.

    Mapping: SECTION_KEY_SUBKEY → config[section][key][subkey]

    Examples:
        SONARR_URL → config['sonarr']['url']
        EXCLUDE_GENRES → config['exclude']['genres']
        SYNC_POLL_INTERVAL → config['sync']['poll_interval']

    List values use comma separation:
        EXCLUDE_GENRES=Reality,Talk Show,Game Show

    Note: Selections cannot be configured via environment variables.
    """
    ...

def validate_config(config: Config) -> None:
    """
    Validate configuration completeness and correctness.

    Checks:
    - Required fields present (sonarr.url, sonarr.api_key, sonarr.root_folder)
    - Valid types (port is int, poll_interval parses to duration)
    - Valid enum values (logging.level, logging.format)
    - No conflicting settings

    Raises:
        ConfigurationError: With details of all validation failures
    """
    ...
```

### Config Dataclasses

```python
@dataclass(frozen=True)
class TVMazeConfig:
    api_key: Optional[str] = None
    rate_limit: int = 20
    update_window: str = "week"  # day, week, month

@dataclass(frozen=True)
class SyncConfig:
    poll_interval: str = "6h"
    retry_delay: str = "1w"
    abandon_after: str = "1y"

# Date range for filtering
@dataclass(frozen=True)
class DateRange:
    after: Optional[str] = None   # ISO date: YYYY-MM-DD
    before: Optional[str] = None  # ISO date: YYYY-MM-DD

# Integer range for filtering
@dataclass(frozen=True)
class IntRange:
    min: Optional[int] = None
    max: Optional[int] = None

# Float range for filtering
@dataclass(frozen=True)
class FloatRange:
    min: Optional[float] = None
    max: Optional[float] = None

# Global exclusion rules - shows matching ANY are rejected
@dataclass(frozen=True)
class GlobalExclude:
    genres: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    networks: list[str] = field(default_factory=list)

# Selection rule - show must match ALL criteria within one selection
@dataclass(frozen=True)
class Selection:
    name: Optional[str] = None
    languages: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    networks: list[str] = field(default_factory=list)
    status: list[str] = field(default_factory=list)
    premiered: Optional[DateRange] = None
    ended: Optional[DateRange] = None
    rating: Optional[FloatRange] = None
    runtime: Optional[IntRange] = None

# Filter configuration with global excludes and selections
@dataclass(frozen=True)
class FiltersConfig:
    exclude: GlobalExclude = field(default_factory=GlobalExclude)
    selections: list[Selection] = field(default_factory=list)

@dataclass(frozen=True)
class SonarrConfig:
    url: str
    api_key: str
    root_folder: str
    quality_profile: str | int
    language_profile: Optional[str | int] = None
    monitor: str = "all"
    search_on_add: bool = True
    tags: list[str | int] = field(default_factory=list)

@dataclass(frozen=True)
class StorageConfig:
    path: str = "/data"

@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    format: str = "json"  # json, text

@dataclass(frozen=True)
class ServerConfig:
    enabled: bool = True
    port: int = 8080

@dataclass(frozen=True)
class Config:
    tvmaze: TVMazeConfig
    sync: SyncConfig
    filters: FiltersConfig
    sonarr: SonarrConfig
    storage: StorageConfig
    logging: LoggingConfig
    server: ServerConfig
    dry_run: bool = True  # Safe default
```

---

## database.py

SQLite database operations for the show cache.

### Database Class

```python
class Database:
    """SQLite database wrapper for show cache."""

    def __init__(self, path: Path):
        """
        Initialize database connection.

        Creates database file and schema if not exists.
        Enables WAL mode for better concurrency.
        """
        ...

    def close(self) -> None:
        """Close database connection."""
        ...

    # ============ Show CRUD ============

    def upsert_show(self, show: Show) -> None:
        """
        Insert or update a show.

        Uses INSERT OR REPLACE with all fields.
        Automatically updates updated_at timestamp.
        """
        ...

    def get_show(self, tvmaze_id: int) -> Optional[Show]:
        """Get show by TVMaze ID."""
        ...

    def get_show_by_tvdb(self, tvdb_id: int) -> Optional[Show]:
        """Get show by TVDB ID."""
        ...

    def delete_show(self, tvmaze_id: int) -> bool:
        """Delete show by TVMaze ID. Returns True if deleted."""
        ...

    # ============ Bulk Operations ============

    def upsert_shows(self, shows: list[Show]) -> int:
        """
        Bulk upsert shows.

        Uses executemany for efficiency.
        Returns count of rows affected.
        """
        ...

    def get_shows_by_status(
        self,
        status: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> list[Show]:
        """Get all shows with given processing status."""
        ...

    def get_shows_for_retry(self, now: datetime) -> list[Show]:
        """
        Get shows ready for retry.

        Returns shows where:
        - processing_status = 'pending_tvdb'
        - retry_after <= now
        - pending_since > (now - abandon_after)
        """
        ...

    def get_all_filtered_shows(self) -> Iterator[Show]:
        """
        Iterate all filtered shows.

        Uses server-side cursor for memory efficiency.
        Used for filter re-evaluation.
        """
        ...

    # ============ Statistics ============

    def get_status_counts(self) -> dict[str, int]:
        """
        Get count of shows by processing status.

        Returns: {"added": 1203, "filtered": 67102, ...}
        """
        ...

    def get_filter_reason_counts(self) -> dict[str, int]:
        """
        Get count of filtered shows by reason.

        Returns: {"genre": 23451, "language": 31204, ...}
        """
        ...

    def get_highest_tvmaze_id(self) -> int:
        """Get highest TVMaze ID in database."""
        ...

    def get_total_count(self) -> int:
        """Get total show count."""
        ...

    def get_retry_counts(self) -> dict[str, int]:
        """Get count of shows pending retry by reason."""
        ...

    # ============ Sync Helpers ============

    def get_tvmaze_ids_updated_since(self, timestamp: int) -> set[int]:
        """Get TVMaze IDs with tvmaze_updated_at >= timestamp."""
        ...

    def mark_show_added(
        self,
        tvmaze_id: int,
        sonarr_series_id: int
    ) -> None:
        """Mark show as added to Sonarr."""
        ...

    def mark_show_filtered(
        self,
        tvmaze_id: int,
        reason: str,
        category: str
    ) -> None:
        """Mark show as filtered with reason."""
        ...

    def mark_show_pending_tvdb(
        self,
        tvmaze_id: int,
        retry_after: datetime
    ) -> None:
        """Mark show as pending TVDB ID with retry time."""
        ...

    def mark_show_failed(
        self,
        tvmaze_id: int,
        error_message: str
    ) -> None:
        """Mark show as permanently failed."""
        ...

    def increment_retry_count(self, tvmaze_id: int) -> int:
        """Increment retry count and return new value."""
        ...
```

### Schema Management

```python
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

-- Indexes
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
    ...

def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version."""
    ...

def migrate_schema(conn: sqlite3.Connection, from_version: int) -> None:
    """Run schema migrations."""
    ...
```

---

## state.py

JSON operational state management with backup/restore.

### SyncState Class

```python
@dataclass
class SyncState:
    """Operational state persisted between runs."""

    last_full_sync: Optional[datetime] = None
    last_incremental_sync: Optional[datetime] = None
    last_tvmaze_page: int = 0
    highest_tvmaze_id: int = 0
    last_filter_hash: Optional[str] = None
    last_updates_check: Optional[datetime] = None

    @classmethod
    def load(cls, path: Path) -> "SyncState":
        """
        Load state from JSON file.

        Recovery logic:
        1. Try loading state.json
        2. If corrupt/missing, try state.json.bak
        3. If both fail, return fresh state

        Logs warnings on recovery.
        """
        ...

    def save(self, path: Path) -> None:
        """
        Save state to JSON file atomically.

        Process:
        1. Serialize to JSON
        2. Write to state.json.tmp
        3. Atomic rename to state.json
        """
        ...

    def backup(self, path: Path) -> None:
        """
        Create backup of current state.

        Copies state.json to state.json.bak.
        Called only after successful sync cycle completion.
        """
        ...

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON encoding."""
        ...

    @classmethod
    def from_dict(cls, data: dict) -> "SyncState":
        """Deserialize from dictionary."""
        ...


def validate_state(data: dict) -> bool:
    """
    Validate state JSON structure.

    Checks:
    - Required keys present
    - Values are correct types
    - Dates parse correctly

    Returns False if invalid (triggers backup restore).
    """
    ...
```

---

## processor.py

Show filtering and processing logic.

### ShowProcessor Class

```python
class ShowProcessor:
    """
    Evaluates shows against configured filters.

    Designed with clean interface to allow future replacement
    with rule engine implementation.
    """

    def __init__(self, config: FiltersConfig, sonarr_config: SonarrConfig):
        self.config = config
        self.sonarr_config = sonarr_config
        self._validated_sonarr_params: Optional[dict] = None

    def set_validated_sonarr_params(
        self,
        root_folder_id: int,
        quality_profile_id: int,
        language_profile_id: Optional[int],
        tag_ids: list[int]
    ) -> None:
        """Set pre-validated Sonarr parameters."""
        ...

    def process(self, show: Show) -> ProcessingResult:
        """
        Evaluate show against filters and return decision.

        Filter evaluation order:
        1. Check TVDB ID exists → SKIP if missing
        2. Check genres → FILTER if excluded genre
        3. Check type → FILTER if not in included types
        4. Check language → FILTER if not in included languages
        5. Check country → FILTER if not in included countries
        6. Check status → FILTER if ended and exclude_ended=true
        7. Check premiered date → FILTER if before threshold
        8. Check runtime → FILTER if below minimum
        9. All passed → ADD

        Returns ProcessingResult with decision and details.
        """
        ...

    def _check_tvdb_id(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show has TVDB ID."""
        if show.tvdb_id is None:
            return ProcessingResult(
                decision=Decision.RETRY,
                reason="No TVDB ID available",
                filter_category="tvdb"
            )
        return None

    def _check_genres(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show has excluded genres."""
        if not self.config.genres.exclude:
            return None

        excluded = set(self.config.genres.exclude)
        show_genres = set(show.genres)
        overlap = excluded & show_genres

        if overlap:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Excluded genre: {', '.join(overlap)}",
                filter_category="genre"
            )
        return None

    def _check_type(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show type is in included list."""
        if not self.config.types.include:
            return None

        if show.type not in self.config.types.include:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Type not included: {show.type}",
                filter_category="type"
            )
        return None

    def _check_language(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show language is in included list."""
        if not self.config.languages.include:
            return None

        if show.language not in self.config.languages.include:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Language not included: {show.language}",
                filter_category="language"
            )
        return None

    def _check_country(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show country is in included list."""
        if not self.config.countries.include:
            return None

        if show.country not in self.config.countries.include:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Country not included: {show.country}",
                filter_category="country"
            )
        return None

    def _check_status(self, show: Show) -> Optional[ProcessingResult]:
        """Check if ended shows should be excluded."""
        if not self.config.status.exclude_ended:
            return None

        if show.status == "Ended":
            return ProcessingResult(
                decision=Decision.FILTER,
                reason="Show has ended",
                filter_category="status"
            )
        return None

    def _check_premiered(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show premiered after threshold."""
        if not self.config.premiered.after:
            return None

        threshold = date.fromisoformat(self.config.premiered.after)
        if show.premiered and show.premiered < threshold:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Premiered before {self.config.premiered.after}",
                filter_category="premiered"
            )
        return None

    def _check_runtime(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show meets minimum runtime."""
        if not self.config.min_runtime:
            return None

        if show.runtime and show.runtime < self.config.min_runtime:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Runtime {show.runtime}m below minimum {self.config.min_runtime}m",
                filter_category="runtime"
            )
        return None

    def _build_sonarr_params(self, show: Show) -> SonarrParams:
        """Build Sonarr parameters for show addition."""
        return SonarrParams(
            tvdb_id=show.tvdb_id,
            title=show.title,
            root_folder=self._validated_sonarr_params['root_folder'],
            quality_profile_id=self._validated_sonarr_params['quality_profile_id'],
            language_profile_id=self._validated_sonarr_params.get('language_profile_id'),
            monitor=self.sonarr_config.monitor,
            search_on_add=self.sonarr_config.search_on_add,
            tags=self._validated_sonarr_params.get('tag_ids', [])
        )


def compute_filter_hash(config: FiltersConfig) -> str:
    """
    Compute hash of filter configuration.

    Used to detect filter changes between runs.
    Returns 16-character hex string.
    """
    import hashlib
    import json

    filter_dict = {
        "genres_exclude": sorted(config.genres.exclude),
        "types_include": sorted(config.types.include),
        "countries_include": sorted(config.countries.include),
        "languages_include": sorted(config.languages.include),
        "exclude_ended": config.status.exclude_ended,
        "premiered_after": config.premiered.after,
        "min_runtime": config.min_runtime,
    }

    serialized = json.dumps(filter_dict, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def check_filter_change(
    state: SyncState,
    config: FiltersConfig,
    db: Database,
    processor: ShowProcessor
) -> int:
    """
    Check for filter changes and re-evaluate if needed.

    Returns count of shows re-evaluated.
    """
    current_hash = compute_filter_hash(config)

    if state.last_filter_hash and state.last_filter_hash != current_hash:
        logger.info("Filter configuration changed, re-evaluating filtered shows...")
        count = re_evaluate_filtered_shows(db, processor)
        state.last_filter_hash = current_hash
        return count

    state.last_filter_hash = current_hash
    return 0


def re_evaluate_filtered_shows(db: Database, processor: ShowProcessor) -> int:
    """
    Re-evaluate all filtered shows against current filters.

    Shows that now pass filters are marked for Sonarr addition.
    Returns count of shows that changed status.
    """
    changed = 0

    for show in db.get_all_filtered_shows():
        result = processor.process(show)

        if result.decision == Decision.ADD:
            # Was filtered, now passes
            db.update_show_status(show.tvmaze_id, ProcessingStatus.PENDING)
            changed += 1
        elif result.decision == Decision.FILTER:
            # Still filtered, possibly different reason
            if result.reason != show.filter_reason:
                db.mark_show_filtered(
                    show.tvmaze_id,
                    result.reason,
                    result.filter_category
                )

    return changed
```

---

## clients/tvmaze.py

TVMaze API client with rate limiting.

```python
class TVMazeClient:
    """
    TVMaze API client.

    Handles:
    - Rate limiting (20 requests / 10 seconds)
    - Automatic retry on 429
    - Response parsing
    """

    BASE_URL = "https://api.tvmaze.com"

    def __init__(self, config: TVMazeConfig):
        self.config = config
        self.session = requests.Session()
        self._rate_limiter = RateLimiter(
            max_requests=config.rate_limit,
            window_seconds=10
        )

        if config.api_key:
            self.session.params['apikey'] = config.api_key

    def get_shows_page(self, page: int) -> list[dict]:
        """
        Get paginated show index.

        GET /shows?page={page}

        Returns list of show dicts, empty list if 404 (end of pages).
        """
        ...

    def get_show(self, tvmaze_id: int) -> dict:
        """
        Get single show details.

        GET /shows/{id}

        Raises TVMazeNotFoundError if 404.
        """
        ...

    def get_updates(self, since: str = "week") -> dict[int, int]:
        """
        Get updated show IDs.

        GET /updates/shows?since={since}

        Returns: {tvmaze_id: unix_timestamp, ...}
        """
        ...

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make rate-limited request.

        Handles:
        - Rate limiting with backoff
        - Retry on 429
        - Metric tracking
        """
        ...


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """
        Block until request is allowed.

        Implements sliding window rate limiting.
        """
        ...

    def wait_time(self) -> float:
        """Get seconds until next request is allowed."""
        ...


class TVMazeError(Exception):
    """Base TVMaze API error."""
    pass

class TVMazeNotFoundError(TVMazeError):
    """Show not found (404)."""
    pass

class TVMazeRateLimitError(TVMazeError):
    """Rate limit exceeded (429)."""
    pass
```

---

## clients/sonarr.py

Sonarr API client wrapping pyarr with validation.

```python
from pyarr import SonarrAPI

class SonarrClient:
    """
    Sonarr API client with startup validation.

    Wraps pyarr SonarrAPI with:
    - Configuration validation
    - Name-to-ID resolution
    - Error handling
    - Metric tracking
    """

    def __init__(self, config: SonarrConfig):
        self.config = config
        self._api = SonarrAPI(config.url, config.api_key)

        # Populated by validate_config()
        self._root_folder_path: Optional[str] = None
        self._quality_profile_id: Optional[int] = None
        self._language_profile_id: Optional[int] = None
        self._tag_ids: list[int] = []
        self._sonarr_version: Optional[str] = None

    def validate_config(self) -> None:
        """
        Validate Sonarr configuration at startup.

        Checks:
        1. API connectivity
        2. Sonarr version detection
        3. Root folder exists
        4. Quality profile exists
        5. Language profile exists (v3 only)
        6. Tags exist

        Raises ConfigurationError with details on failure.
        """
        self._validate_connection()
        self._validate_root_folder()
        self._validate_quality_profile()
        self._validate_language_profile()
        self._validate_tags()

    def _validate_connection(self) -> None:
        """Verify API connectivity and detect version."""
        try:
            status = self._api.get_system_status()
            self._sonarr_version = status.get('version', 'unknown')
            logger.info(f"Connected to Sonarr {self._sonarr_version}")
        except Exception as e:
            raise ConfigurationError(f"Cannot connect to Sonarr: {e}")

    def _validate_root_folder(self) -> None:
        """Validate configured root folder exists."""
        folders = self._api.get_root_folder()

        by_path = {f['path']: f['id'] for f in folders}
        by_id = {f['id']: f['path'] for f in folders}

        configured = self.config.root_folder

        # Check if configured as ID
        if isinstance(configured, int) or (isinstance(configured, str) and configured.isdigit()):
            folder_id = int(configured)
            if folder_id not in by_id:
                raise ConfigurationError(
                    f"Root folder ID {folder_id} not found. "
                    f"Available: {list(by_id.values())}"
                )
            self._root_folder_path = by_id[folder_id]
        else:
            # Configured as path
            if configured not in by_path:
                raise ConfigurationError(
                    f"Root folder '{configured}' not found. "
                    f"Available: {list(by_path.keys())}"
                )
            self._root_folder_path = configured

    def _validate_quality_profile(self) -> None:
        """Validate configured quality profile exists."""
        profiles = self._api.get_quality_profile()

        by_name = {p['name'].lower(): p['id'] for p in profiles}
        by_id = {p['id']: p['name'] for p in profiles}

        configured = self.config.quality_profile

        if isinstance(configured, int):
            if configured not in by_id:
                raise ConfigurationError(
                    f"Quality profile ID {configured} not found. "
                    f"Available: {[f\"{p['name']} ({p['id']})\" for p in profiles]}"
                )
            self._quality_profile_id = configured
        else:
            if configured.lower() not in by_name:
                raise ConfigurationError(
                    f"Quality profile '{configured}' not found. "
                    f"Available: {[p['name'] for p in profiles]}"
                )
            self._quality_profile_id = by_name[configured.lower()]

    def _validate_language_profile(self) -> None:
        """Validate language profile (Sonarr v3 only)."""
        # Check if Sonarr v4+ (no language profiles)
        if self._sonarr_version and self._sonarr_version.startswith('4'):
            self._language_profile_id = None
            return

        if not self.config.language_profile:
            raise ConfigurationError(
                "language_profile required for Sonarr v3"
            )

        profiles = self._api.get_language_profile()
        # Similar validation logic...

    def _validate_tags(self) -> None:
        """Validate configured tags exist."""
        if not self.config.tags:
            self._tag_ids = []
            return

        tags = self._api.get_tag()
        by_name = {t['label'].lower(): t['id'] for t in tags}
        by_id = {t['id']: t['label'] for t in tags}

        self._tag_ids = []
        for configured in self.config.tags:
            if isinstance(configured, int):
                if configured not in by_id:
                    raise ConfigurationError(
                        f"Tag ID {configured} not found. "
                        f"Available: {[f\"{t['label']} ({t['id']})\" for t in tags]}"
                    )
                self._tag_ids.append(configured)
            else:
                if configured.lower() not in by_name:
                    raise ConfigurationError(
                        f"Tag '{configured}' not found. "
                        f"Available: {[t['label'] for t in tags]}"
                    )
                self._tag_ids.append(by_name[configured.lower()])

    @property
    def validated_params(self) -> dict:
        """Get validated Sonarr parameters."""
        return {
            'root_folder': self._root_folder_path,
            'quality_profile_id': self._quality_profile_id,
            'language_profile_id': self._language_profile_id,
            'tag_ids': self._tag_ids,
        }

    def lookup_series(self, tvdb_id: int) -> Optional[dict]:
        """
        Lookup series by TVDB ID.

        Returns series dict if found, None otherwise.
        """
        try:
            results = self._api.lookup_series(term=f"tvdb:{tvdb_id}")
            return results[0] if results else None
        except Exception as e:
            logger.warning(f"Sonarr lookup failed for TVDB {tvdb_id}: {e}")
            return None

    def add_series(self, params: SonarrParams, series_data: dict) -> AddResult:
        """
        Add series to Sonarr.

        Returns AddResult indicating success/exists/failed.
        """
        try:
            result = self._api.add_series(
                series=series_data,
                quality_profile_id=params.quality_profile_id,
                language_profile_id=params.language_profile_id,
                root_dir=params.root_folder,
                monitored=True,
                search_for_missing_episodes=params.search_on_add,
                tags=params.tags
            )
            return AddResult(success=True, series_id=result.get('id'))

        except Exception as e:
            if 'already been added' in str(e).lower():
                return AddResult(success=False, exists=True)
            return AddResult(success=False, error=str(e))

    def is_healthy(self) -> bool:
        """Check if Sonarr is reachable."""
        try:
            self._api.get_system_status()
            return True
        except:
            return False


@dataclass
class AddResult:
    success: bool
    series_id: Optional[int] = None
    exists: bool = False
    error: Optional[str] = None
```

---

## scheduler.py

Sync cycle scheduling.

```python
class Scheduler:
    """
    Manages sync cycle scheduling.

    Features:
    - Configurable interval
    - Manual trigger support
    - Graceful shutdown
    - Thread-safe
    """

    def __init__(
        self,
        interval: timedelta,
        sync_func: Callable[[], None]
    ):
        self.interval = interval
        self.sync_func = sync_func
        self._stop_event = threading.Event()
        self._trigger_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_run: Optional[datetime] = None
        self._running = False

    def start(self) -> None:
        """Start scheduler in background thread."""
        ...

    def stop(self, timeout: float = 300) -> None:
        """
        Stop scheduler gracefully.

        Waits for current cycle to complete up to timeout seconds.
        """
        ...

    def trigger_now(self) -> None:
        """Trigger immediate sync cycle."""
        ...

    @property
    def next_run(self) -> Optional[datetime]:
        """Get next scheduled run time."""
        return self._next_run

    @property
    def is_running(self) -> bool:
        """Check if sync is currently running."""
        return self._running

    def _run_loop(self) -> None:
        """Main scheduler loop."""
        while not self._stop_event.is_set():
            self._next_run = datetime.utcnow() + self.interval

            # Wait for interval or trigger
            triggered = self._trigger_event.wait(
                timeout=self.interval.total_seconds()
            )
            self._trigger_event.clear()

            if self._stop_event.is_set():
                break

            # Run sync
            self._running = True
            try:
                self.sync_func()
            except Exception as e:
                logger.exception("Sync cycle failed")
            finally:
                self._running = False
```

---

## server.py

Flask HTTP server for health, metrics, and API.

```python
from flask import Flask, jsonify, request
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

def create_app(
    db: Database,
    state: SyncState,
    scheduler: Scheduler,
    sonarr: SonarrClient,
    config: Config
) -> Flask:
    """Create Flask application."""

    app = Flask(__name__)

    @app.route('/health')
    def health():
        """Liveness probe."""
        return jsonify({"status": "ok"})

    @app.route('/ready')
    def ready():
        """
        Readiness probe.

        Checks:
        - Database accessible
        - Sonarr reachable
        """
        checks = {
            "database": db.is_healthy(),
            "sonarr": sonarr.is_healthy(),
        }

        all_healthy = all(checks.values())
        status_code = 200 if all_healthy else 503

        return jsonify({
            "status": "ready" if all_healthy else "not_ready",
            "checks": checks
        }), status_code

    @app.route('/metrics')
    def metrics():
        """Prometheus metrics endpoint."""
        update_db_metrics(db)
        return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

    @app.route('/trigger', methods=['POST'])
    def trigger():
        """Manually trigger sync cycle."""
        if scheduler.is_running:
            return jsonify({
                "status": "already_running",
                "message": "Sync cycle already in progress"
            }), 409

        scheduler.trigger_now()
        return jsonify({"status": "triggered"})

    @app.route('/state')
    def get_state():
        """Get current operational state."""
        return jsonify({
            "last_full_sync": state.last_full_sync.isoformat() if state.last_full_sync else None,
            "last_incremental_sync": state.last_incremental_sync.isoformat() if state.last_incremental_sync else None,
            "highest_tvmaze_id": state.highest_tvmaze_id,
            "next_scheduled_run": scheduler.next_run.isoformat() if scheduler.next_run else None,
            "sync_running": scheduler.is_running,
            **db.get_status_counts()
        })

    @app.route('/shows')
    def list_shows():
        """
        Query shows.

        Query params:
        - status: Filter by processing status
        - limit: Max results (default 100)
        - offset: Pagination offset
        """
        status = request.args.get('status')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        shows = db.get_shows_by_status(
            status=status,
            limit=min(limit, 1000),
            offset=offset
        )

        return jsonify({
            "shows": [s.to_dict() for s in shows],
            "count": len(shows),
            "limit": limit,
            "offset": offset
        })

    @app.route('/refilter', methods=['POST'])
    def refilter():
        """Force re-evaluation of all filtered shows."""
        from .processor import re_evaluate_filtered_shows

        count = re_evaluate_filtered_shows(db, processor)
        return jsonify({
            "status": "complete",
            "shows_re_evaluated": count
        })

    return app
```

---

## metrics.py

Prometheus metric definitions.

```python
from prometheus_client import Counter, Gauge

# ============ Sync Health ============
sync_last_run_timestamp = Gauge(
    'tvmaze_sync_last_run_timestamp',
    'Unix timestamp of last completed sync'
)
sync_last_run_duration_seconds = Gauge(
    'tvmaze_sync_last_run_duration_seconds',
    'Duration of last sync cycle'
)
sync_next_run_timestamp = Gauge(
    'tvmaze_sync_next_run_timestamp',
    'Unix timestamp of next scheduled sync'
)
sync_initial_complete = Gauge(
    'tvmaze_sync_initial_complete',
    'Whether initial full sync has completed (0/1)'
)
sync_healthy = Gauge(
    'tvmaze_sync_healthy',
    'Whether last sync completed successfully (0/1)'
)

# ============ Database State ============
shows_total = Gauge(
    'tvmaze_shows_total',
    'Total shows in database',
    ['status']
)
shows_filtered_by_reason = Gauge(
    'tvmaze_shows_filtered_by_reason',
    'Shows filtered by reason',
    ['reason']
)
shows_highest_id = Gauge(
    'tvmaze_shows_highest_id',
    'Highest TVMaze ID seen'
)

# ============ Processing Activity ============
shows_processed_total = Counter(
    'tvmaze_shows_processed_total',
    'Total shows processed (lifetime)',
    ['result']
)
sync_shows_processed = Gauge(
    'tvmaze_sync_shows_processed',
    'Shows processed in last sync cycle',
    ['result']
)

# ============ External APIs ============
api_requests_total = Counter(
    'tvmaze_api_requests_total',
    'External API requests',
    ['service', 'endpoint', 'status']
)
sonarr_healthy = Gauge(
    'tvmaze_sonarr_healthy',
    'Sonarr API reachable (0/1)'
)

# ============ Retry Queue ============
shows_pending_retry = Gauge(
    'tvmaze_shows_pending_retry',
    'Shows awaiting retry',
    ['reason']
)


def update_db_metrics(db: Database) -> None:
    """Refresh gauges from database state."""
    # Status counts
    counts = db.get_status_counts()
    for status, count in counts.items():
        shows_total.labels(status=status).set(count)

    # Filter reason counts
    filter_counts = db.get_filter_reason_counts()
    for reason, count in filter_counts.items():
        shows_filtered_by_reason.labels(reason=reason).set(count)

    # Highest ID
    shows_highest_id.set(db.get_highest_tvmaze_id())

    # Retry counts
    retry_counts = db.get_retry_counts()
    for reason, count in retry_counts.items():
        shows_pending_retry.labels(reason=reason).set(count)


def record_sync_complete(stats: SyncStats, success: bool) -> None:
    """Record metrics after sync completion."""
    sync_last_run_timestamp.set(stats.completed_at.timestamp())
    sync_last_run_duration_seconds.set(stats.duration_seconds)
    sync_healthy.set(1 if success else 0)

    # Per-cycle results
    sync_shows_processed.labels(result='added').set(stats.shows_added)
    sync_shows_processed.labels(result='filtered').set(stats.shows_filtered)
    sync_shows_processed.labels(result='skipped').set(stats.shows_skipped)
    sync_shows_processed.labels(result='failed').set(stats.shows_failed)
    sync_shows_processed.labels(result='exists').set(stats.shows_exists)

    # Lifetime counters
    shows_processed_total.labels(result='added').inc(stats.shows_added)
    shows_processed_total.labels(result='filtered').inc(stats.shows_filtered)
    shows_processed_total.labels(result='skipped').inc(stats.shows_skipped)
    shows_processed_total.labels(result='failed').inc(stats.shows_failed)
    shows_processed_total.labels(result='exists').inc(stats.shows_exists)
```

---

## main.py

Application entry point and orchestration.

```python
import signal
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def main():
    """Application entry point."""

    # ============ Load Configuration ============
    config_path = Path(os.environ.get('CONFIG_PATH', '/config/config.yaml'))
    try:
        config = load_config(config_path)
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # ============ Configure Logging ============
    setup_logging(config.logging)
    logger.info("Starting TVMaze-Sync")

    # ============ Validate External Dependencies ============
    sonarr = SonarrClient(config.sonarr)
    try:
        sonarr.validate_config()
    except ConfigurationError as e:
        logger.error(f"Sonarr configuration invalid: {e}")
        sys.exit(1)

    tvmaze = TVMazeClient(config.tvmaze)

    # ============ Initialize Storage ============
    storage_path = Path(config.storage.path)
    storage_path.mkdir(parents=True, exist_ok=True)

    db = Database(storage_path / "shows.db")
    state = SyncState.load(storage_path / "state.json")

    # ============ Initialize Processor ============
    processor = ShowProcessor(config.filters, config.sonarr)
    processor.set_validated_sonarr_params(**sonarr.validated_params)

    # ============ Check Filter Changes ============
    check_filter_change(state, config.filters, db, processor)

    # ============ Create Sync Function ============
    def run_sync():
        sync_cycle(
            db=db,
            state=state,
            config=config,
            sonarr=sonarr,
            tvmaze=tvmaze,
            processor=processor
        )

    # ============ Start Flask Server ============
    app = None
    if config.server.enabled:
        from .server import create_app
        app = create_app(db, state, scheduler, sonarr, config)
        flask_thread = threading.Thread(
            target=lambda: app.run(
                host='0.0.0.0',
                port=config.server.port,
                threaded=True
            )
        )
        flask_thread.daemon = True
        flask_thread.start()
        logger.info(f"HTTP server listening on port {config.server.port}")

    # ============ Start Scheduler ============
    interval = parse_duration(config.sync.poll_interval)
    scheduler = Scheduler(interval=interval, sync_func=run_sync)

    # ============ Signal Handling ============
    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        scheduler.stop(timeout=300)
        db.close()
        state.save(storage_path / "state.json")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # ============ Log Startup Banner ============
    log_startup_banner(config, state, db)

    # ============ Start Scheduler ============
    scheduler.start()

    # Run initial sync immediately if needed
    if state.last_full_sync is None:
        logger.info("No previous sync detected, starting initial sync...")
        scheduler.trigger_now()

    # Block main thread
    try:
        while True:
            signal.pause()
    except AttributeError:
        # Windows doesn't have signal.pause
        while True:
            time.sleep(1)


def sync_cycle(
    db: Database,
    state: SyncState,
    config: Config,
    sonarr: SonarrClient,
    tvmaze: TVMazeClient,
    processor: ShowProcessor
) -> None:
    """Execute a single sync cycle."""

    stats = SyncStats(started_at=datetime.utcnow())
    storage_path = Path(config.storage.path)

    try:
        if state.last_full_sync is None:
            # Initial full sync
            run_initial_sync(db, state, config, sonarr, tvmaze, processor, stats)
            state.last_full_sync = datetime.utcnow()
        else:
            # Incremental sync
            run_incremental_sync(db, state, config, sonarr, tvmaze, processor, stats)

        # Retry pending_tvdb shows
        retry_pending_tvdb(db, state, config, sonarr, tvmaze, processor, stats)

        # Update state
        state.last_incremental_sync = datetime.utcnow()
        state.save(storage_path / "state.json")
        state.backup(storage_path / "state.json")

        stats.completed_at = datetime.utcnow()
        record_sync_complete(stats, success=True)

        logger.info(
            f"Sync complete: {stats.shows_added} added, "
            f"{stats.shows_filtered} filtered, "
            f"{stats.shows_exists} already existed"
        )

    except Exception as e:
        logger.exception("Sync cycle failed")
        stats.completed_at = datetime.utcnow()
        record_sync_complete(stats, success=False)
        raise


def run_initial_sync(db, state, config, sonarr, tvmaze, processor, stats):
    """Paginate through all TVMaze shows."""
    logger.info("Starting initial full sync...")
    page = state.last_tvmaze_page

    while True:
        try:
            shows_data = tvmaze.get_shows_page(page)
            if not shows_data:
                break  # End of pages

            for show_data in shows_data:
                show = Show.from_tvmaze_response(show_data)
                process_single_show(db, config, sonarr, processor, show, stats)
                state.highest_tvmaze_id = max(state.highest_tvmaze_id, show.tvmaze_id)

            # Checkpoint progress
            state.last_tvmaze_page = page
            state.save(Path(config.storage.path) / "state.json")

            logger.debug(f"Processed page {page}, {len(shows_data)} shows")
            page += 1

        except TVMazeRateLimitError:
            logger.warning("Rate limited, backing off...")
            time.sleep(10)
            continue

    sync_initial_complete.set(1)
    logger.info(f"Initial sync complete, processed {stats.shows_processed} shows")


def run_incremental_sync(db, state, config, sonarr, tvmaze, processor, stats):
    """Check for updated shows since last sync."""
    logger.info("Starting incremental sync...")

    updates = tvmaze.get_updates(since=config.tvmaze.update_window)
    logger.info(f"Found {len(updates)} updated shows")

    for tvmaze_id, updated_at in updates.items():
        existing = db.get_show(tvmaze_id)

        # Process if new or updated
        if not existing or (existing.tvmaze_updated_at or 0) < updated_at:
            try:
                show_data = tvmaze.get_show(tvmaze_id)
                show = Show.from_tvmaze_response(show_data)
                process_single_show(db, config, sonarr, processor, show, stats)
                state.highest_tvmaze_id = max(state.highest_tvmaze_id, tvmaze_id)
            except TVMazeNotFoundError:
                logger.warning(f"Show {tvmaze_id} not found, skipping")
            except TVMazeRateLimitError:
                logger.warning("Rate limited, backing off...")
                time.sleep(10)


def process_single_show(db, config, sonarr, processor, show, stats):
    """Process a single show through filters and Sonarr."""
    stats.shows_processed += 1

    # Store show in database
    show.last_checked = datetime.utcnow()
    db.upsert_show(show)

    # Skip if dry run
    if config.dry_run:
        result = processor.process(show)
        logger.info(f"[DRY RUN] {show.title}: {result.decision.value}")
        return

    # Process through filters
    result = processor.process(show)

    if result.decision == Decision.FILTER:
        db.mark_show_filtered(show.tvmaze_id, result.reason, result.filter_category)
        stats.shows_filtered += 1

    elif result.decision == Decision.RETRY:
        retry_after = datetime.utcnow() + parse_duration(config.sync.retry_delay)
        db.mark_show_pending_tvdb(show.tvmaze_id, retry_after)
        stats.shows_skipped += 1

    elif result.decision == Decision.ADD:
        # Lookup and add to Sonarr
        series_data = sonarr.lookup_series(show.tvdb_id)
        if not series_data:
            db.mark_show_pending_tvdb(show.tvmaze_id, retry_after)
            stats.shows_skipped += 1
            return

        add_result = sonarr.add_series(result.sonarr_params, series_data)

        if add_result.success:
            db.mark_show_added(show.tvmaze_id, add_result.series_id)
            stats.shows_added += 1
            logger.info(f"Added: {show.title}")
        elif add_result.exists:
            db.update_show_status(show.tvmaze_id, ProcessingStatus.EXISTS)
            stats.shows_exists += 1
        else:
            db.mark_show_failed(show.tvmaze_id, add_result.error)
            stats.shows_failed += 1
            logger.warning(f"Failed to add {show.title}: {add_result.error}")


if __name__ == "__main__":
    main()
```
