# TVMaze-Sync

> Automated TV show discovery and Sonarr integration powered by TVMaze API

TVMaze-Sync is a Docker-native service that automatically discovers TV shows from TVMaze and adds them to Sonarr based on configurable filters. It maintains a local SQLite cache for efficient syncing and instant filter re-evaluation.

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/andronics/tvmaze-sync/pkgs/container/tvmaze-sync)
[![Docker Pulls](https://img.shields.io/docker/pulls/andronics/tvmaze-sync)](https://github.com/andronics/tvmaze-sync/pkgs/container/tvmaze-sync)

## Features

- ✅ **Automated Discovery**: Automatically sync TV shows from TVMaze to Sonarr
- 🎯 **Smart Filtering**: Filter shows by genre, language, country, type, status, premiere date, and runtime
- 💾 **Efficient Caching**: SQLite database cache (~70k shows, ~15-20MB)
- 🔄 **Incremental Syncing**: Initial full sync, then efficient incremental updates
- 🧪 **Dry Run Mode**: Test filters without actually adding shows to Sonarr
- 📊 **Prometheus Metrics**: Built-in metrics for monitoring
- 🔍 **HTTP API**: RESTful endpoints for status, manual triggers, and queries
- 🐳 **Docker Native**: Full Docker and docker-compose support
- 🔐 **Secrets Support**: Docker secrets for API keys
- ⚡ **Rate Limiting**: Built-in TVMaze API rate limiting (20 req/10s)

## Quick Start

### Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/andronics/tvmaze-sync.git
cd tvmaze-sync

# Create configuration
cp config.example.yaml config.yaml
# Edit config.yaml with your Sonarr details

# Run with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f
```

### Docker

```bash
docker run -d \
  --name tvmaze-sync \
  -v /path/to/config:/config \
  -v /path/to/data:/data \
  -e SONARR_URL=http://sonarr:8989 \
  -e SONARR_API_KEY=your-api-key \
  -e SONARR_ROOT_FOLDER=/tv \
  -e SONARR_QUALITY_PROFILE=HD-1080p \
  -p 8080:8080 \
  ghcr.io/andronics/tvmaze-sync:latest
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package with dependencies
pip install -e .

# Or install development dependencies
pip install -e ".[dev]"

# Run the application
CONFIG_PATH=./config.yaml tvmaze-sync

# Or use the module directly
python -m src.main
```

## Configuration

Configuration is done via `config.yaml` or environment variables. All config values support `${VAR}` and `${VAR_FILE}` (Docker secrets) patterns.

### Minimal Configuration

```yaml
sonarr:
  url: "${SONARR_URL}"
  api_key: "${SONARR_API_KEY}"
  root_folder: "/tv"
  quality_profile: "HD-1080p"

filters:
  languages:
    include: ["English"]
```

### Full Configuration

See `config.example.yaml` for all available options.

```yaml
tvmaze:
  api_key: "${TVMAZE_API_KEY}"      # Optional premium key for higher rate limits
  rate_limit: 20                     # Requests per 10 seconds (20 for free, 100 for premium)
  update_window: "week"              # day, week, or month

sync:
  poll_interval: "6h"                # How often to sync (s, m, h, d, w, y)
  retry_delay: "1w"                  # Retry pending_tvdb shows after this delay
  abandon_after: "1y"                # Abandon pending_tvdb shows after this time

filters:
  genres:
    exclude: ["Reality", "Talk Show", "Game Show", "News", "Sports"]

  languages:
    include: ["English"]             # Filter by language

  countries:
    include: ["US", "GB", "CA"]      # ISO 3166-1 country codes (GB, not UK)

  types:
    include: ["Scripted"]            # Scripted, Reality, Documentary, etc.

  status:
    exclude_ended: true              # Skip ended shows

  premiered_after: "2020-01-01"      # Minimum premiere date (YYYY-MM-DD)

  min_runtime: 20                    # Minimum runtime in minutes

sonarr:
  url: "${SONARR_URL}"
  api_key: "${SONARR_API_KEY}"
  root_folder: "/tv"                 # Path or folder ID
  quality_profile: "HD-1080p"        # Name or profile ID
  language_profile: "English"        # Sonarr v3 only (auto-detected)
  monitor: "all"                     # all, future, missing, existing, pilot, etc.
  search_on_add: true
  tags: ["tvmaze", "auto"]           # Optional tags

storage:
  path: "/data"                      # Data directory for database and state

logging:
  level: "INFO"                      # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json"                     # json or text

server:
  enabled: true
  port: 8080

dry_run: false                       # Test mode - don't actually add to Sonarr
```

## Environment Variables

All configuration options can be set via environment variables using `SECTION_KEY_SUBKEY` naming convention:

### Required Variables

| Variable | Description |
|----------|-------------|
| `SONARR_URL` | Sonarr base URL (e.g., `http://localhost:8989`) |
| `SONARR_API_KEY` | Sonarr API key |
| `SONARR_ROOT_FOLDER` | Root folder path or ID |
| `SONARR_QUALITY_PROFILE` | Quality profile name or ID |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CONFIG_PATH` | Path to config file | `/config/config.yaml` |
| `TVMAZE_API_KEY` | TVMaze premium API key | (none) |
| `TVMAZE_RATE_LIMIT` | Requests per 10 seconds | `20` |
| `TVMAZE_UPDATE_WINDOW` | Update check window | `week` |
| `SYNC_POLL_INTERVAL` | Sync frequency | `6h` |
| `SYNC_RETRY_DELAY` | Retry pending_tvdb after | `1w` |
| `SYNC_ABANDON_AFTER` | Abandon pending_tvdb after | `1y` |
| `FILTERS_GENRES_EXCLUDE` | Comma-separated genres | (none) |
| `FILTERS_LANGUAGES_INCLUDE` | Comma-separated languages | (none) |
| `FILTERS_COUNTRIES_INCLUDE` | Comma-separated countries | (none) |
| `FILTERS_TYPES_INCLUDE` | Comma-separated types | (none) |
| `FILTERS_STATUS_EXCLUDE_ENDED` | Skip ended shows | `true` |
| `FILTERS_PREMIERED_AFTER` | Minimum premiere date | (none) |
| `FILTERS_MIN_RUNTIME` | Minimum runtime minutes | (none) |
| `SONARR_LANGUAGE_PROFILE` | Language profile (v3 only) | (none) |
| `SONARR_MONITOR` | Monitor mode | `all` |
| `SONARR_SEARCH_ON_ADD` | Search after adding | `true` |
| `SONARR_TAGS` | Comma-separated tags | (none) |
| `STORAGE_PATH` | Data directory | `/data` |
| `LOGGING_LEVEL` | Log level | `INFO` |
| `LOGGING_FORMAT` | Log format (json/text) | `json` |
| `SERVER_ENABLED` | Enable HTTP server | `true` |
| `SERVER_PORT` | HTTP server port | `8080` |
| `DRY_RUN` | Don't actually add to Sonarr | `false` |

### Docker Secrets Support

For sensitive values, use the `_FILE` suffix to read from a file (useful for Docker secrets):

```yaml
sonarr:
  api_key: "${SONARR_API_KEY_FILE}"
```

```bash
# Docker Compose with secrets
docker-compose.yml:
  secrets:
    - sonarr_api_key
  environment:
    - SONARR_API_KEY_FILE=/run/secrets/sonarr_api_key
```

## API Endpoints

The built-in HTTP server exposes several endpoints for monitoring and control:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Liveness probe (always returns 200 if running) |
| `/ready` | GET | Readiness probe (checks Sonarr connectivity) |
| `/metrics` | GET | Prometheus metrics |
| `/trigger` | POST | Manually trigger a sync cycle |
| `/state` | GET | Current sync state (last run times, page info) |
| `/shows` | GET | Query shows from database |
| `/refilter` | POST | Re-evaluate filters for all filtered shows |

### API Examples

```bash
# Trigger manual sync
curl -X POST http://localhost:8080/trigger

# Check current state
curl http://localhost:8080/state

# Query filtered shows
curl "http://localhost:8080/shows?status=filtered&limit=10"

# Query added shows
curl "http://localhost:8080/shows?status=added"

# Re-evaluate filters after config change
curl -X POST http://localhost:8080/refilter
```

## Dry Run Mode

Test your filters without actually adding shows to Sonarr:

```bash
# Via environment variable
DRY_RUN=true docker-compose up

# Via config.yaml
dry_run: true

# Check logs to see what would be added
docker logs tvmaze-sync | grep "DRY RUN"
```

Dry run mode will:
- Fetch shows from TVMaze
- Apply all filters
- Log decisions (add/filter/skip)
- NOT add shows to Sonarr
- Still update the database

## Monitoring

### Prometheus Metrics

Metrics are exposed at `/metrics` in Prometheus format:

```
# Sync health and timing
tvmaze_sync_last_run_timestamp         # Unix timestamp of last sync
tvmaze_sync_healthy                    # 1 if healthy, 0 if unhealthy
tvmaze_sync_initial_complete           # 1 if initial sync completed

# Show counts by status
tvmaze_shows_total{status="added"}     # Shows added to Sonarr
tvmaze_shows_total{status="filtered"}  # Shows filtered out
tvmaze_shows_total{status="pending"}   # Shows pending TVDB ID
tvmaze_shows_total{status="failed"}    # Shows that failed to add
tvmaze_shows_total{status="exists"}    # Shows already in Sonarr

# External service health
tvmaze_sonarr_healthy                  # 1 if Sonarr reachable, 0 otherwise
```

### Grafana Dashboard

Example Prometheus queries:

```promql
# Shows added in last 24h
increase(tvmaze_shows_total{status="added"}[24h])

# Filter rejection rate
rate(tvmaze_shows_total{status="filtered"}[1h])

# Time since last successful sync
time() - tvmaze_sync_last_run_timestamp
```

### Database Inspection

```bash
# Access database
docker exec -it tvmaze-sync sqlite3 /data/shows.db

# Show counts by status
SELECT processing_status, COUNT(*) FROM shows GROUP BY processing_status;

# Find filtered shows by reason
SELECT title, filter_reason FROM shows WHERE processing_status='filtered' LIMIT 20;

# Shows by genre
SELECT title, genres FROM shows WHERE genres LIKE '%Drama%' LIMIT 10;

# Check pending retries
SELECT title, retry_after, retry_count FROM shows WHERE processing_status='pending_tvdb';
```

### State Inspection

```bash
# View current state
cat data/state.json | jq .

# Or via API
curl http://localhost:8080/state | jq .
```

### Log Analysis

```bash
# Follow logs in Docker
docker logs -f tvmaze-sync

# JSON log filtering (if using json format)
docker logs tvmaze-sync 2>&1 | jq 'select(.level=="ERROR")'

# Filter for added shows
docker logs tvmaze-sync | grep "Added:"
```

## Troubleshooting

### Initial sync taking long?
- **Normal**: ~70k shows with 20 req/10s rate limit takes several hours
- **Progress is checkpointed**: Safe to restart - resumes from last page
- **Premium API key**: Upgrade to 100 req/10s for faster sync

### Show not added?
Check filter reason:
```bash
curl "http://localhost:8080/shows?status=filtered" | jq '.[] | {title, filter_reason}'
```

Test with dry run mode:
```bash
DRY_RUN=true docker-compose restart tvmaze-sync
docker logs -f tvmaze-sync
```

### Missing TVDB ID?
Some shows don't have TVDB IDs in TVMaze:
- Marked as `pending_tvdb`
- Retried weekly (configurable via `SYNC_RETRY_DELAY`)
- Abandoned after 1 year (configurable via `SYNC_ABANDON_AFTER`)
- After abandon time, marked as `failed`

```bash
# Check pending shows
sqlite3 /data/shows.db "SELECT title, retry_count FROM shows WHERE processing_status='pending_tvdb';"
```

### Filters not working?
Re-evaluate filters after config change:
```bash
curl -X POST http://localhost:8080/refilter
```

This will:
- Re-process all filtered shows
- Apply new filter criteria
- Add shows that now pass filters
- Fast (local SQLite queries, no API calls)

### Sonarr connection errors?
Check validation at startup:
```bash
docker logs tvmaze-sync | grep -i sonarr
```

Validates:
- Sonarr connectivity
- Root folder exists
- Quality profile exists
- Tags exist (if configured)

### Country codes?
TVMaze uses ISO 3166-1 country codes:
- ✅ Use `GB` (not `UK`)
- ✅ Use `US` (not `USA`)
- See: https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2

## Architecture

### Project Structure

```
tvmaze-sync/
├── pyproject.toml           # Package configuration
├── config.example.yaml      # Example configuration
├── Dockerfile
├── docker-compose.yml
├── src/
│   ├── main.py              # Entry point, orchestration
│   ├── config.py            # Config loading, env var resolution
│   ├── models.py            # Dataclasses (Show, ProcessingResult, etc.)
│   ├── database.py          # SQLite operations
│   ├── state.py             # JSON state management
│   ├── processor.py         # Show filtering logic
│   ├── scheduler.py         # Sync scheduling
│   ├── server.py            # Flask HTTP server
│   ├── metrics.py           # Prometheus metrics
│   └── clients/
│       ├── tvmaze.py        # TVMaze API client
│       └── sonarr.py        # Sonarr client (pyarr wrapper)
├── tests/
└── data/                    # Runtime data (not in repo)
    ├── state.json           # Sync state
    ├── state.json.bak       # State backup
    └── shows.db             # SQLite cache
```

### Tech Stack

- **Python 3.12+**
- **SQLite** - Show metadata cache (~70k shows, ~15-20MB)
- **Flask** - HTTP server for health/metrics/API
- **pyarr** - Sonarr API client library
- **prometheus_client** - Metrics exposition
- **requests** - TVMaze API client
- **PyYAML** - Configuration parsing

### Storage Architecture

**Hybrid Storage (SQLite + JSON)**

- **SQLite (shows.db)**: All show metadata and processing state
  - ~70k shows
  - ~15-20MB on disk
  - Indexed queries for fast filter re-evaluation
  - Handles large datasets efficiently

- **JSON (state.json)**: Lightweight operational state
  - Sync progress (last page, highest ID)
  - Last run timestamps
  - Filter hash (for change detection)
  - Human-readable, easy to inspect

### Sync Process

1. **Initial Full Sync** (first run)
   - Paginate through entire TVMaze index (~70k shows)
   - 250 shows per page
   - Progress checkpointed every page
   - Rate limited (20 req/10s default)
   - Resumes from last page on restart

2. **Incremental Sync** (subsequent runs)
   - Fetch updated shows since last sync (day/week/month window)
   - Check for new shows beyond highest known ID
   - Much faster than full sync

3. **Filter Re-evaluation** (on filter config change)
   - Detects filter changes via hash comparison
   - Re-processes all filtered shows
   - Local SQLite queries (no API calls)
   - Fast (~67k shows in seconds)

4. **Pending TVDB Retries**
   - Shows without TVDB IDs marked `pending_tvdb`
   - Retried weekly (configurable)
   - Max 4 retries (configurable)
   - Marked `failed` after max retries

### Filter Processing

Shows are processed through a filter chain:

1. **TVDB ID**: Must have TVDB ID (or marked pending_tvdb)
2. **Genre**: Exclude unwanted genres
3. **Language**: Include only specific languages
4. **Country**: Include only specific countries
5. **Type**: Include only specific types (Scripted, Reality, etc.)
6. **Status**: Exclude ended shows (optional)
7. **Premiere Date**: Must premiere after specified date
8. **Runtime**: Must meet minimum runtime

First filter that rejects → show filtered with reason

### External APIs

**TVMaze API**
- Base URL: `https://api.tvmaze.com`
- Rate limit: 20 req/10s (100 with premium key)
- No auth required (optional premium key)
- Endpoints used:
  - `GET /shows?page=N` - Paginated index
  - `GET /shows/:id` - Single show details
  - `GET /updates/shows?since=week` - Updated shows

**Sonarr API**
- Library: pyarr
- Auth: API key in header
- Version detection: Auto-detects v3 vs v4
- Operations:
  - `get_system_status()` - Health check
  - `get_root_folder()` - Validate root folder
  - `get_quality_profile()` - Validate quality profile
  - `lookup_series(term="tvdb:123")` - Find show
  - `add_series(...)` - Add to library

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/andronics/tvmaze-sync.git
cd tvmaze-sync

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run only unit tests
pytest -m unit

# Run specific test file
pytest tests/test_processor.py

# Watch mode (requires pytest-watch)
ptw
```

### Code Style

The codebase follows these conventions:

**Type Hints** - Use modern Python 3.12+ syntax:
```python
def get_show(self, tvmaze_id: int) -> Show | None:
    ...

def get_shows(self, status: str | None = None) -> list[Show]:
    ...
```

**Dataclasses** - For data structures:
```python
@dataclass(frozen=True)
class SonarrConfig:
    url: str
    api_key: str
```

**Error Handling**:
- Custom exception classes
- Fail fast on startup
- Resilient during runtime
- Log errors with context

**Database**:
- Parameterized queries (never string formatting)
- Context managers for transactions
- Index columns used in WHERE clauses

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run test suite
6. Submit pull request

### Building Docker Image

```bash
# Build
docker build -t tvmaze-sync:latest .

# Build with build args
docker build --build-arg PYTHON_VERSION=3.12 -t tvmaze-sync:latest .

# Multi-platform build
docker buildx build --platform linux/amd64,linux/arm64 -t tvmaze-sync:latest .
```

## Known Issues

### Sonarr v3 vs v4
Language profiles are required in v3 but don't exist in v4. The client auto-detects the version and adjusts accordingly. If using v3, you must specify `language_profile` in config.

### Filter Re-evaluation Logging
Changing filters triggers re-evaluation of ~67k filtered shows. This is fast (SQLite indexed queries) but generates many log entries. This is normal and expected behavior.

### TVMaze Rate Limiting
- Free tier: 20 requests per 10 seconds
- Initial sync of 70k shows takes several hours
- Premium key increases to 100 req/10s (5x faster)
- Progress is checkpointed - safe to restart

### Docker Volume Permissions
If running into permission issues:
```bash
# Fix ownership
chown -R 1000:1000 /path/to/data /path/to/config

# Or run as root (not recommended)
docker run --user root ...
```

## Documentation

- [ARCHITECTURE.md](.github/ARCHITECTURE.md) - Detailed system design and data flow
- [MODULES.md](.github/MODULES.md) - Module specifications and interfaces
- [config.example.yaml](config.example.yaml) - Configuration reference

## Support

- **Issues**: https://github.com/andronics/tvmaze-sync/issues
- **Discussions**: https://github.com/andronics/tvmaze-sync/discussions

## License

MIT License - see LICENSE file for details

## Acknowledgments

- [TVMaze](https://www.tvmaze.com/) - TV show data API
- [Sonarr](https://sonarr.tv/) - PVR for TV shows
- [pyarr](https://github.com/totaldebug/pyarr) - Python API client for Sonarr
