# TVMaze-Sync Architecture

> Automated TV show discovery and Sonarr integration powered by TVMaze API

## Overview

TVMaze-Sync is a Docker-native service that monitors the TVMaze database for TV shows matching configurable criteria and automatically adds them to Sonarr. It maintains a local SQLite cache of show metadata, enabling efficient incremental syncs and instant filter re-evaluation without re-fetching data.

## Core Principles

1. **Fail Fast** - Validate all configuration and external dependencies at startup
2. **Idempotent Operations** - Safe to restart at any point without data corruption
3. **Efficient Syncing** - Initial full sync, then incremental updates via TVMaze's updates endpoint
4. **Local Intelligence** - Cache enough metadata to re-evaluate filters without API calls
5. **Observable** - Prometheus metrics, health endpoints, structured logging

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            TVMaze-Sync Container                         │
│                                                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐ │
│  │   Scheduler  │────▶│  Sync Engine │────▶│  Processor (Filtering)   │ │
│  └──────────────┘     └──────────────┘     └──────────────────────────┘ │
│         │                    │                          │                │
│         │                    ▼                          ▼                │
│         │            ┌──────────────┐          ┌──────────────┐         │
│         │            │ TVMaze Client│          │ Sonarr Client│         │
│         │            └──────────────┘          └──────────────┘         │
│         │                    │                          │                │
│         │                    ▼                          │                │
│         │            ┌──────────────────────────────────┴───┐           │
│         │            │         SQLite (shows.db)            │           │
│         │            │   - Show metadata cache              │           │
│         │            │   - Processing status                │           │
│         │            │   - Filter reasons                   │           │
│         │            └──────────────────────────────────────┘           │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Flask Server (:8080)                           │   │
│  │  GET /health    GET /ready    GET /metrics    POST /trigger       │   │
│  │  GET /state     GET /shows    POST /refilter                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────┐                                                    │
│  │  state.json     │  Operational state (last sync, progress, etc.)     │
│  │  state.json.bak │  Backup after successful cycles                    │
│  └─────────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
   ┌─────────────┐                ┌─────────────┐
   │  TVMaze API │                │  Sonarr API │
   │  (external) │                │  (internal) │
   └─────────────┘                └─────────────┘
```

## Data Flow

### Initial Sync (First Run)

```
1. Paginate through TVMaze /shows?page=0,1,2...
2. For each show:
   a. Store full metadata in SQLite
   b. Evaluate against filters
   c. If passes: lookup in Sonarr, add if not exists
   d. Update processing_status in SQLite
3. Checkpoint progress to state.json after each page
4. Mark initial sync complete
```

### Incremental Sync (Subsequent Runs)

```
1. GET /updates/shows?since=week
2. For each updated TVMaze ID:
   a. Check if exists in SQLite
   b. If new or updated: GET /shows/:id for full data
   c. Upsert metadata in SQLite
   d. Evaluate against filters
   e. If passes: add to Sonarr
3. Check for new shows beyond highest known ID
4. Process retry queue (pending_tvdb shows)
```

### Filter Change Detection

```
1. On startup: compute hash of filter configuration
2. Compare against stored hash in state.json
3. If changed:
   a. Query all shows with status='filtered' from SQLite
   b. Re-evaluate each against new filters (no API calls)
   c. Shows that now pass: queue for Sonarr addition
   d. Update stored filter hash
```

## Storage Architecture

### SQLite Database (shows.db)

Primary data store for show metadata and processing state.

```sql
CREATE TABLE shows (
    -- TVMaze identifiers
    tvmaze_id INTEGER PRIMARY KEY,
    tvdb_id INTEGER,
    imdb_id TEXT,

    -- Show metadata (for filtering)
    title TEXT NOT NULL,
    language TEXT,
    country TEXT,
    type TEXT,              -- Scripted, Reality, Animation, etc.
    status TEXT,            -- Running, Ended, In Development, etc.
    premiered DATE,
    ended DATE,
    network TEXT,
    web_channel TEXT,
    genres TEXT,            -- JSON array stored as text
    runtime INTEGER,

    -- Processing state
    processing_status TEXT NOT NULL DEFAULT 'pending',
    filter_reason TEXT,     -- Why it was filtered (for metrics)
    sonarr_series_id INTEGER,
    added_to_sonarr_at DATETIME,

    -- Sync metadata
    last_checked DATETIME NOT NULL,
    tvmaze_updated_at INTEGER,  -- Unix timestamp from TVMaze
    retry_after DATETIME,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,

    -- Record timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_processing_status ON shows(processing_status);
CREATE INDEX idx_tvdb_id ON shows(tvdb_id);
CREATE INDEX idx_language ON shows(language);
CREATE INDEX idx_country ON shows(country);
CREATE INDEX idx_type ON shows(type);
CREATE INDEX idx_premiered ON shows(premiered);
CREATE INDEX idx_retry_after ON shows(retry_after);
CREATE INDEX idx_tvmaze_updated_at ON shows(tvmaze_updated_at);
```

**Processing Status Values:**
| Status | Description |
|--------|-------------|
| `pending` | New, not yet processed |
| `filtered` | Excluded by filters (reason stored in filter_reason) |
| `pending_tvdb` | No TVDB ID available, will retry |
| `added` | Successfully added to Sonarr |
| `exists` | Already existed in Sonarr |
| `failed` | Sonarr rejected, permanent failure |
| `skipped` | Manually excluded |

### JSON State (state.json)

Lightweight operational state, separate from show data.

```json
{
  "last_full_sync": "2025-01-15T10:30:00Z",
  "last_incremental_sync": "2025-01-15T16:30:00Z",
  "last_tvmaze_page": 280,
  "highest_tvmaze_id": 70123,
  "last_filter_hash": "a1b2c3d4e5f6g7h8",
  "last_updates_check": "2025-01-15T10:00:00Z"
}
```

**State File Safety:**
1. Write to `state.json.tmp`
2. Atomic rename to `state.json`
3. Backup to `state.json.bak` only after successful full cycle

**Corruption Recovery:**
1. On load: validate JSON structure
2. If corrupt: restore from `state.json.bak`
3. If backup also corrupt: start fresh, log error

## Configuration

### YAML Configuration (config.yaml)

```yaml
tvmaze:
  api_key: "${TVMAZE_API_KEY}"          # Optional premium key
  rate_limit: 20                         # Requests per 10 seconds
  update_window: "week"                  # day, week, month

sync:
  poll_interval: "6h"                    # How often to sync
  retry_delay: "1w"                      # Retry pending_tvdb after
  abandon_after: "1y"                    # Abandon pending_tvdb after

filters:
  genres:
    exclude: ["Reality", "Talk Show", "Game Show", "News", "Sports"]
  types:
    include: ["Scripted", "Animation", "Documentary"]
  countries:
    include: ["US", "UK", "CA", "AU", "NZ", "IE", "GB"]
  languages:
    include: ["English"]
  status:
    exclude_ended: true
  premiered:
    after: "2010-01-01"
  min_runtime: 20

sonarr:
  url: "${SONARR_URL}"
  api_key: "${SONARR_API_KEY}"
  root_folder: "/tv"
  quality_profile: "HD-1080p"
  language_profile: "English"
  monitor: "all"
  search_on_add: true
  tags: ["auto-sync"]

storage:
  path: "/data"

logging:
  level: "INFO"                          # DEBUG, INFO, WARNING, ERROR
  format: "json"                         # json, text

server:
  enabled: true
  port: 8080

dry_run: false
```

### Environment Variable Resolution

All config values support environment variable substitution:

- `${VAR}` - Direct environment variable
- `${VAR_FILE}` - Read value from file (Docker secrets pattern)

```python
# Resolution order for ${SONARR_API_KEY}:
1. Check for SONARR_API_KEY_FILE env var → read file contents
2. Check for SONARR_API_KEY env var → use value directly
3. Raise ConfigurationError if neither exists
```

### Full Environment Override

Every config option can be set via environment variable:

```bash
TVMAZE_API_KEY=xxx
TVMAZE_RATE_LIMIT=20
TVMAZE_UPDATE_WINDOW=week
SYNC_POLL_INTERVAL=6h
SYNC_RETRY_DELAY=1w
SYNC_ABANDON_AFTER=1y
FILTERS_GENRES_EXCLUDE=Reality,Talk Show,Game Show
FILTERS_LANGUAGES_INCLUDE=English
SONARR_URL=http://sonarr:8989
SONARR_API_KEY=xxx
SONARR_ROOT_FOLDER=/tv
SONARR_QUALITY_PROFILE=HD-1080p
STORAGE_PATH=/data
LOGGING_LEVEL=INFO
SERVER_PORT=8080
DRY_RUN=false
```

## External Integrations

### TVMaze API

**Base URL:** `https://api.tvmaze.com`

**Endpoints Used:**
| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `GET /shows?page=N` | Paginated show index (250/page) | Cached 24h |
| `GET /shows/:id` | Single show details | Standard |
| `GET /updates/shows?since=week` | Updated show IDs | Cached 60min |

**Rate Limiting:**
- 20 requests per 10 seconds per IP
- Implement exponential backoff on HTTP 429
- Respect cache headers

**Response Mapping:**
```python
TVMaze Response → SQLite Row
─────────────────────────────
id              → tvmaze_id
externals.thetvdb → tvdb_id
externals.imdb  → imdb_id
name            → title
language        → language
network.country.code → country (or webChannel.country.code)
type            → type
status          → status
premiered       → premiered
ended           → ended
network.name    → network
webChannel.name → web_channel
genres          → genres (JSON string)
runtime         → runtime
updated         → tvmaze_updated_at
```

### Sonarr API

**Library:** pyarr (https://github.com/totaldebug/pyarr)

**Startup Validation:**
1. `GET /api/v3/system/status` - Verify connectivity, detect version
2. `GET /api/v3/rootfolder` - Validate configured root folder exists
3. `GET /api/v3/qualityprofile` - Validate quality profile exists
4. `GET /api/v3/languageprofile` - Validate language profile (v3 only)
5. `GET /api/v3/tag` - Validate configured tags exist

**Adding Shows:**
```python
# 1. Lookup by TVDB ID
results = sonarr.lookup_series(term=f"tvdb:{tvdb_id}")

# 2. Add to library
sonarr.add_series(
    series=results[0],
    quality_profile_id=validated_profile_id,
    language_profile_id=validated_language_id,  # v3 only
    root_dir=validated_root_folder,
    monitored=True,
    search_for_missing_episodes=config.search_on_add,
    tags=validated_tag_ids
)
```

**Error Handling:**
| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 201 | Created | Mark as `added` |
| 409 | Already exists | Mark as `exists` |
| 400 | Bad request | Mark as `failed`, log error |
| 404 | TVDB ID not found | Mark as `pending_tvdb` if no TVDB, else `failed` |

## HTTP Server

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness probe - always returns 200 if server running |
| `/ready` | GET | Readiness probe - checks DB and Sonarr connectivity |
| `/metrics` | GET | Prometheus metrics endpoint |
| `/trigger` | POST | Manually trigger sync cycle |
| `/state` | GET | Current operational state summary |
| `/shows` | GET | Query shows (supports `?status=` filter) |
| `/refilter` | POST | Force re-evaluation of all filtered shows |

### Prometheus Metrics

**Sync Health:**
- `tvmaze_sync_last_run_timestamp` - Unix timestamp of last completed sync
- `tvmaze_sync_last_run_duration_seconds` - Duration of last sync cycle
- `tvmaze_sync_next_run_timestamp` - Unix timestamp of next scheduled sync
- `tvmaze_sync_initial_complete` - Whether initial full sync has completed (0/1)
- `tvmaze_sync_healthy` - Whether last sync completed successfully (0/1)

**Database State:**
- `tvmaze_shows_total{status}` - Total shows by processing status
- `tvmaze_shows_filtered_by_reason{reason}` - Filter breakdown
- `tvmaze_shows_highest_id` - Highest TVMaze ID seen

**Processing Activity:**
- `tvmaze_shows_processed_total{result}` - Lifetime counter by result
- `tvmaze_sync_shows_processed{result}` - Last cycle counter by result

**External APIs:**
- `tvmaze_api_requests_total{service,endpoint,status}` - API call counter
- `tvmaze_sonarr_healthy` - Sonarr reachable (0/1)

**Retry Queue:**
- `tvmaze_shows_pending_retry{reason}` - Shows awaiting retry

## Startup Sequence

```
1. Load configuration
   ├── Parse YAML
   ├── Resolve environment variables
   └── Validate schema

2. Validate external dependencies
   ├── Sonarr: connectivity, root folder, quality profile, tags
   └── TVMaze: connectivity (optional API key validation)

3. Initialize storage
   ├── Open/create SQLite database
   ├── Run migrations if needed
   ├── Load state.json (or restore from backup)
   └── Verify state integrity

4. Check for filter changes
   └── Re-evaluate filtered shows if config changed

5. Start Flask server
   └── Health/metrics/API endpoints available

6. Start scheduler
   └── Begin sync cycles

7. Log startup banner
   └── Config summary (secrets redacted)
```

## Shutdown Sequence

```
1. Receive SIGTERM/SIGINT

2. Stop scheduler
   └── Prevent new cycles from starting

3. Wait for current cycle to complete
   └── Configurable timeout (default: 5 minutes)

4. Save final state
   ├── Flush pending database writes
   └── Save state.json

5. Stop Flask server

6. Exit cleanly
```

## Error Handling

### Transient Errors (Retry)
- Network timeouts
- HTTP 429 (rate limited)
- HTTP 5xx (server errors)
- Database locked

### Permanent Errors (Don't Retry)
- HTTP 400 (bad request)
- HTTP 401/403 (auth failure)
- Invalid TVDB ID (mark pending_tvdb)
- Schema validation failure

### Recovery Strategies

**State Corruption:**
```
state.json corrupt → restore state.json.bak
state.json.bak corrupt → start fresh (initial sync)
```

**Database Corruption:**
```
SQLite corrupt → log error, exit (manual intervention required)
```

**Mid-Sync Failure:**
```
Progress checkpointed after each page → resume from last page
Show-level failure → log, continue with next show
```

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

VOLUME ["/data", "/config"]

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
```

### Docker Compose

```yaml
services:
  tvmaze-sync:
    image: tvmaze-sync:latest
    container_name: tvmaze-sync
    environment:
      - SONARR_URL=http://sonarr:8989
      - SONARR_API_KEY_FILE=/run/secrets/sonarr_api_key
      - TVMAZE_API_KEY_FILE=/run/secrets/tvmaze_api_key
    volumes:
      - ./config.yaml:/config/config.yaml:ro
      - tvmaze-data:/data
    secrets:
      - sonarr_api_key
      - tvmaze_api_key
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    depends_on:
      - sonarr

secrets:
  sonarr_api_key:
    file: ./secrets/sonarr_api_key.txt
  tvmaze_api_key:
    file: ./secrets/tvmaze_api_key.txt

volumes:
  tvmaze-data:
```

## Future Considerations

### Rule Engine (v2)

The processor module is designed with a clean interface to allow future replacement of simple filter logic with a full rule engine:

```python
class ShowProcessor(ABC):
    @abstractmethod
    def process(self, show: Show) -> ProcessingResult:
        pass

# v1: SimpleFilterProcessor (current)
# v2: RuleEngineProcessor (future)
```

Potential rule engine features:
- Route to different Sonarr quality profiles by network
- Multiple Sonarr instance support
- Complex conditional logic
- Tag assignment based on rules

### Additional Integrations

- **Radarr** - Movie support using same pattern
- **Notifications** - Webhook/Discord/Gotify on show additions
- **Manual Review Queue** - Web UI for approving borderline shows
