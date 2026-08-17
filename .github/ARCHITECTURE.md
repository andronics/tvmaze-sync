# TVMaze-Sync Architecture

> Automated TV show discovery and Sonarr integration powered by TVMaze API

## Overview

TVMaze-Sync is a Docker-native service that monitors the TVMaze database for TV shows matching configurable criteria and automatically adds them to Sonarr. It maintains a local SQLite cache of show metadata, enabling efficient incremental syncs and instant filter re-evaluation without re-fetching data.

The service includes a full web UI for monitoring, browsing shows, and managing configuration.

## Core Principles

1. **Fail Fast** - Validate all configuration and external dependencies at startup
2. **Idempotent Operations** - Safe to restart at any point without data corruption
3. **Efficient Syncing** - Initial full sync, then incremental updates via TVMaze's updates endpoint
4. **Local Intelligence** - Cache enough metadata to re-evaluate filters without API calls
5. **Observable** - Prometheus metrics, health endpoints, structured logging, web dashboard

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            TVMaze-Sync Container                                 │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                       Flask HTTP Server (:5000)                            │ │
│  │                                                                            │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │ │
│  │  │                         Web UI (Jinja2 + HTMX)                      │  │ │
│  │  │                                                                     │  │ │
│  │  │   /              Dashboard    - Status, stats, sync control         │  │ │
│  │  │   /ui/shows      Shows        - Browse, search, filter 85k shows    │  │ │
│  │  │   /ui/config     Config       - View running configuration          │  │ │
│  │  │   /ui/api        API Docs     - Endpoint reference                  │  │ │
│  │  │   /ui/about      About        - Setup guide, documentation          │  │ │
│  │  │   /login         Login        - API key authentication              │  │ │
│  │  │                                                                     │  │ │
│  │  │   /ui/partials/* HTMX         - Dynamic partial updates             │  │ │
│  │  └─────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                            │ │
│  │  ┌──────────────────────┐  ┌──────────────────────┐  ┌─────────────────┐  │ │
│  │  │   Public Endpoints   │  │  Protected API       │  │  Static Assets  │  │ │
│  │  │                      │  │                      │  │                 │  │ │
│  │  │   GET /health        │  │  POST /trigger       │  │  /static/css/   │  │ │
│  │  │   GET /ready         │  │  GET  /state         │  │  /static/js/    │  │ │
│  │  │   GET /metrics       │  │  GET  /shows         │  │                 │  │ │
│  │  │                      │  │  POST /refilter      │  │  Tailwind CSS   │  │ │
│  │  │                      │  │  GET  /config        │  │  (CDN)          │  │ │
│  │  └──────────────────────┘  └──────────────────────┘  └─────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                        │                                         │
│                                        │ reads/writes                            │
│                                        ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                              Main Application                              │ │
│  │                                                                            │ │
│  │  ┌──────────────┐    triggers    ┌──────────────────────────────────────┐ │ │
│  │  │  Scheduler   │ ─────────────► │            Sync Engine               │ │ │
│  │  │              │                │                                      │ │ │
│  │  │ - interval   │                │  1. Fetch shows from TVMaze          │ │ │
│  │  │ - is_running │                │  2. Store in database                │ │ │
│  │  │ - next_run   │                │  3. Apply filters (Processor)        │ │ │
│  │  │              │                │  4. Add matches to Sonarr            │ │ │
│  │  └──────────────┘                │  5. Update state                     │ │ │
│  │                                  └──────────────────────────────────────┘ │ │
│  │                                        │                                  │ │
│  │                    ┌───────────────────┼───────────────────┐              │ │
│  │                    ▼                   ▼                   ▼              │ │
│  │  ┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐  │ │
│  │  │    TVMaze Client     │ │    Processor     │ │    Sonarr Client     │  │ │
│  │  │                      │ │                  │ │                      │  │ │
│  │  │ - fetch all shows    │ │ - global exclude │ │ - validate config    │  │ │
│  │  │ - fetch updates      │ │ - selections     │ │ - add series         │  │ │
│  │  │ - rate limiting      │ │ - filter logic   │ │ - check exists       │  │ │
│  │  └──────────────────────┘ └──────────────────┘ └──────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                        │                                         │
│                                        ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │                              Storage Layer                                   ││
│  │                                                                              ││
│  │   ┌─────────────────────────────┐    ┌─────────────────────────────┐        ││
│  │   │     SQLite Database         │    │       JSON State            │        ││
│  │   │     /data/shows.db          │    │     /data/state.json        │        ││
│  │   │                             │    │                             │        ││
│  │   │  - ~85k shows cached        │    │  - last_full_sync           │        ││
│  │   │  - processing_status        │    │  - last_incremental_sync    │        ││
│  │   │  - filter_reason            │    │  - highest_tvmaze_id        │        ││
│  │   │  - retry tracking           │    │  - last_tvmaze_page         │        ││
│  │   │  - search indexes           │    │  - last_filter_hash         │        ││
│  │   └─────────────────────────────┘    └─────────────────────────────┘        ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│   Volumes: /data (persistent), /config (config.yaml)                            │
└─────────────────────────────────────────────────────────────────────────────────┘
         │                                                        │
         │ HTTPS                                                  │ HTTP
         ▼                                                        ▼
┌─────────────────────┐                              ┌─────────────────────┐
│    TVMaze API       │                              │     Sonarr API      │
│                     │                              │                     │
│ api.tvmaze.com      │                              │ http://sonarr:8989  │
│                     │                              │                     │
│ - GET /shows        │                              │ - GET /series       │
│ - GET /updates      │                              │ - POST /series      │
│ - Rate: 20 req/10s  │                              │ - GET /status       │
└─────────────────────┘                              └─────────────────────┘
```

## Web UI Architecture

### Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Templates | Jinja2 | Server-side HTML rendering |
| Styling | Tailwind CSS (CDN) | Utility-first CSS, no build step |
| Interactivity | HTMX | Dynamic updates without JavaScript frameworks |
| Icons | Heroicons (inline SVG) | Consistent icon set |

### Template Structure

```
src/templates/
├── base.html                   # Base layout (nav, footer, Tailwind, HTMX)
├── login.html                  # API key authentication
├── dashboard.html              # System status and statistics
├── shows.html                  # Shows browser with search/filter
├── config.html                 # Configuration viewer
├── api.html                    # API documentation
├── about.html                  # Setup guide and docs
├── components/
│   ├── nav.html                # Navigation bar with sync status
│   └── footer.html             # Footer with links
├── partials/                   # HTMX partial templates (no base layout)
│   ├── nav_status.html         # Sync status indicator (polled every 10s)
│   ├── sync_status.html        # Dashboard sync panel (polled every 30s)
│   ├── shows_table.html        # Shows table with pagination
│   └── show_detail.html        # Show detail modal content
└── errors/
    ├── 404.html                # Not found page
    └── 500.html                # Server error page
```

### Static Assets

```
src/static/
├── css/
│   └── custom.css              # HTMX transitions, toast animations, status colors
└── js/
    └── app.js                  # Toast notifications, HTMX event handlers
```

### Authentication Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────►│  /login     │────►│  Dashboard  │
│             │     │             │     │             │
│  No cookie  │     │  POST key   │     │  Cookie set │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                          ▼
                    ┌─────────────┐
                    │  Validate   │
                    │  API Key    │
                    │             │
                    │  Match? ────┼──► Set cookie (7 days, httponly)
                    │  No match? ─┼──► Show error
                    └─────────────┘

Authentication Methods (checked in order):
1. X-API-Key header     (API clients)
2. api_key query param  (API clients)
3. api_key cookie       (Web UI)
```

### HTMX Patterns

**Live Status Polling:**
```html
<!-- Nav sync indicator - polls every 10 seconds -->
<div hx-get="/ui/partials/nav-status"
     hx-trigger="every 10s"
     hx-swap="innerHTML">
    {% include 'partials/nav_status.html' %}
</div>
```

**Search with Debounce:**
```html
<!-- Search input with 500ms debounce -->
<input type="text" name="search"
       hx-get="/ui/partials/shows"
       hx-trigger="keyup changed delay:500ms"
       hx-target="#shows-table"
       hx-include="[name='status']">
```

**Filter Updates:**
```html
<!-- Status dropdown triggers instant table update -->
<select name="status"
        hx-get="/ui/partials/shows"
        hx-trigger="change"
        hx-target="#shows-table"
        hx-include="[name='search']">
```

**Modal Loading:**
```html
<!-- Click row to load show detail into modal -->
<tr onclick="showModal({{ show.tvmaze_id }})">

<script>
function showModal(tvmazeId) {
    htmx.ajax('GET', '/ui/partials/show/' + tvmazeId,
              {target: '#modal-content', swap: 'innerHTML'});
    document.getElementById('show-modal').classList.remove('hidden');
}
</script>
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

### Filter Pipeline

```
  Show from TVMaze
         │
         ▼
  ┌─────────────────────────────────────────┐
  │         Stage 1: Global Excludes        │
  │                 (OR logic)              │
  │                                         │
  │  genres[] ─┐                            │
  │  types[]   ├─► ANY match = FILTERED     │
  │  languages[]                            │
  │  countries[]                            │
  │  networks[]─┘                           │
  └─────────────────────────────────────────┘
         │ pass
         ▼
  ┌─────────────────────────────────────────┐
  │        Stage 2: Selections              │
  │     (AND within, OR across)             │
  │                                         │
  │  Selection 1: ──┐                       │
  │    languages[]  │                       │
  │    countries[]  ├─► ALL must match      │
  │    genres[]     │                       │
  │    premiered{}  │                       │
  │    rating{}  ───┘                       │
  │         OR                              │
  │  Selection 2: ──┐                       │
  │    ...       ───┘                       │
  │                                         │
  │  ANY selection match = ADD              │
  │  NO selection match  = FILTERED         │
  └─────────────────────────────────────────┘
         │
         ▼
  ┌─────────────────┐
  │ Check TVDB ID   │
  │                 │
  │ Has ID? ───────►│ ADD to Sonarr
  │                 │
  │ No ID? ────────►│ PENDING_TVDB (retry later)
  └─────────────────┘
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
    rating REAL,            -- TVMaze rating.average (0-10)

    -- Processing state
    processing_status TEXT NOT NULL DEFAULT 'pending',
    filter_reason TEXT,     -- Why it was filtered (for metrics/UI)
    sonarr_series_id INTEGER,
    added_to_sonarr_at DATETIME,

    -- Sync metadata
    last_checked DATETIME NOT NULL,
    tvmaze_updated_at INTEGER,  -- Unix timestamp from TVMaze
    retry_after DATETIME,
    retry_count INTEGER DEFAULT 0,
    pending_since DATETIME,
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
CREATE INDEX idx_pending_since ON shows(pending_since);
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
| `abandoned` | Exceeded retry timeout |

### Web UI Database Methods

Additional methods for the shows browser:

```python
def search_shows(
    status: str = None,
    search: str = None,      # Title LIKE search
    language: str = None,
    country: str = None,
    show_type: str = None,
    genre: str = None,
    limit: int = 50,
    offset: int = 0
) -> list[Show]

def count_shows(...) -> int  # Same filters, returns count

def get_distinct_values(column: str) -> list[str]  # For filter dropdowns

def get_all_genres() -> list[str]  # Extract unique genres from JSON
```

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

# Global exclusions - shows matching ANY are rejected first
exclude:
  genres: ["Reality", "Talk Show", "Game Show", "News", "Sports"]
  types: []
  languages: []
  countries: []
  networks: ["Home Shopping Network"]

# Selections - show must match ALL criteria in at least ONE selection
selections:
  - name: "English Scripted"
    languages: ["English"]
    countries: ["US", "GB", "CA", "AU", "NZ", "IE"]
    types: ["Scripted", "Animation"]
    premiered:
      after: "2010-01-01"
    rating:
      min: 6.0
    runtime:
      min: 20

  - name: "Quality Documentaries"
    types: ["Documentary"]
    rating:
      min: 7.5

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
  port: 5000
  api_key: "${SERVER_API_KEY}"           # Required for web UI and API

dry_run: false  # Defaults to true - set false when ready
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

## HTTP Server

### Routes Overview

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/health` | GET | No | Liveness probe |
| `/ready` | GET | No | Readiness probe (DB + Sonarr) |
| `/metrics` | GET | No | Prometheus metrics |
| `/login` | GET/POST | No | Web UI authentication |
| `/` | GET | Yes | Dashboard |
| `/ui/shows` | GET | Yes | Shows browser |
| `/ui/config` | GET | Yes | Configuration viewer |
| `/ui/api` | GET | Yes | API documentation |
| `/ui/about` | GET | Yes | About/setup guide |
| `/ui/partials/*` | GET | Yes | HTMX partial templates |
| `/trigger` | POST | Yes | Manually trigger sync |
| `/state` | GET | Yes | Operational state JSON |
| `/shows` | GET | Yes | Query shows JSON |
| `/refilter` | POST | Yes | Re-evaluate filtered shows |
| `/config` | GET | Yes | Full config JSON |
| `/logout` | GET | Yes | Clear auth cookie |

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

### Sonarr API

**Library:** pyarr (https://github.com/totaldebug/pyarr)

**Startup Validation:**
1. `GET /api/v3/system/status` - Verify connectivity, detect version
2. `GET /api/v3/rootfolder` - Validate configured root folder exists
3. `GET /api/v3/qualityprofile` - Validate quality profile exists
4. `GET /api/v3/languageprofile` - Validate language profile (v3 only)
5. `GET /api/v3/tag` - Validate configured tags exist

**Error Handling:**
| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 201 | Created | Mark as `added` |
| 409 | Already exists | Mark as `exists` |
| 400 | Bad request | Mark as `failed`, log error |
| 404 | TVDB ID not found | Mark as `pending_tvdb` if no TVDB, else `failed` |

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
   ├── Register templates and static files
   ├── Register template filters (format_datetime, status_color, etc.)
   ├── Register context processors (nav_items, api_key)
   └── Health/metrics/API/Web UI endpoints available

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

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

RUN useradd -m -u 1000 tvmaze && \
    mkdir -p /data /config && \
    chown -R tvmaze:tvmaze /app /data /config

VOLUME ["/data", "/config"]

EXPOSE 5000

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

USER tvmaze

ENV CONFIG_PATH=/config/config.yaml \
    STORAGE_PATH=/data \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["tvmaze-sync"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  tvmaze-sync:
    image: tvmaze-sync:latest
    container_name: tvmaze-sync
    environment:
      - SONARR_URL=http://sonarr:8989
      - SONARR_API_KEY_FILE=/run/secrets/sonarr_api_key
      - TVMAZE_API_KEY_FILE=/run/secrets/tvmaze_api_key
      - SERVER_API_KEY_FILE=/run/secrets/server_api_key
    volumes:
      - ./config.yaml:/config/config.yaml:ro
      - tvmaze-data:/data
    secrets:
      - sonarr_api_key
      - tvmaze_api_key
      - server_api_key
    ports:
      - "5000:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

secrets:
  sonarr_api_key:
    file: ./secrets/sonarr_api_key.txt
  tvmaze_api_key:
    file: ./secrets/tvmaze_api_key.txt
  server_api_key:
    file: ./secrets/server_api_key.txt

volumes:
  tvmaze-data:
```

## Module Structure

```
src/
├── __init__.py
├── main.py              # Entry point, orchestration, sync logic
├── config.py            # Configuration loading and validation
├── models.py            # Data classes (Show, ProcessingResult, etc.)
├── database.py          # SQLite operations, search methods
├── state.py             # JSON state management
├── processor.py         # Show filtering logic
├── scheduler.py         # Sync cycle scheduling
├── server.py            # Flask app, routes, templates
├── metrics.py           # Prometheus metrics
├── clients/
│   ├── __init__.py
│   ├── tvmaze.py        # TVMaze API client
│   └── sonarr.py        # Sonarr API client
├── templates/           # Jinja2 templates (see Web UI Architecture)
└── static/              # CSS and JS assets
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

### Event-Driven Architecture (v3)

For larger scale deployments:
- Message queue (Redis) for decoupled processing
- Separate worker processes for discovery, filtering, target integration
- Plugin system for adding new targets (Plex, Jellyfin, webhooks)
- Async processing with httpx for improved throughput
