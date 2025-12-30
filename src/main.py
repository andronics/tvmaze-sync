"""Application entry point and orchestration."""

import logging
import os
import signal
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .clients.sonarr import SonarrClient
from .clients.tvmaze import TVMazeClient, TVMazeNotFoundError, TVMazeRateLimitError
from .config import Config, ConfigurationError, load_config
from .database import Database
from .metrics import record_sync_complete, sync_initial_complete
from .models import Decision, ProcessingStatus, Show, SyncStats
from .processor import ShowProcessor, check_filter_change
from .scheduler import Scheduler
from .state import SyncState

logger = logging.getLogger(__name__)


def setup_logging(logging_config) -> None:
    """Configure application logging."""
    import logging as log_module
    import logging.config as log_config

    level = getattr(log_module, logging_config.level.upper(), log_module.INFO)

    if logging_config.format == "json":
        # JSON structured logging
        LOGGING_CONFIG = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'json': {
                    'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
                    'datefmt': '%Y-%m-%dT%H:%M:%S'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'json',
                    'stream': 'ext://sys.stdout'
                }
            },
            'root': {
                'level': level,
                'handlers': ['console']
            }
        }
        log_config.dictConfig(LOGGING_CONFIG)
    else:
        # Simple text logging
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def parse_duration(duration_str: str) -> timedelta:
    """Parse duration string like '6h', '30m', '1d', '1w', '1y' to timedelta.

    Supported units:
        s  - seconds
        m  - minutes
        h  - hours
        d  - days
        w  - weeks
        y  - years (converted to 365 days)
    """
    if not duration_str:
        raise ValueError("Duration string cannot be empty")

    if len(duration_str) < 2:
        raise ValueError(f"Invalid duration format: {duration_str}")

    unit = duration_str[-1]
    value_str = duration_str[:-1]

    try:
        value = int(value_str)
    except ValueError:
        raise ValueError(f"Invalid duration value: {value_str}")

    units = {
        's': lambda v: timedelta(seconds=v),
        'm': lambda v: timedelta(minutes=v),
        'h': lambda v: timedelta(hours=v),
        'd': lambda v: timedelta(days=v),
        'w': lambda v: timedelta(weeks=v),
        'y': lambda v: timedelta(days=v * 365),
    }

    if unit not in units:
        raise ValueError(f"Invalid duration unit: {unit}. Use s, m, h, d, w, or y")

    return units[unit](value)


def log_startup_banner(config: Config, state: SyncState, db: Database) -> None:
    """Log startup banner with config summary."""
    logger.info("=" * 70)
    logger.info("TVMaze-Sync Starting")
    logger.info("=" * 70)
    logger.info(f"Sonarr URL: {config.sonarr.url}")
    logger.info(f"TVMaze rate limit: {config.tvmaze.rate_limit} req/10s")
    logger.info(f"Sync interval: {config.sync.poll_interval}")
    logger.info(f"Dry run mode: {config.dry_run}")
    logger.info(f"Last full sync: {state.last_full_sync or 'Never'}")
    logger.info(f"Total shows in DB: {db.get_total_count()}")
    logger.info("=" * 70)


def sync_selections_to_sonarr(
    db: Database,
    config: Config,
    sonarr: SonarrClient,
    processor: ShowProcessor
) -> None:
    """
    Ensure all shows matching selections are in Sonarr.

    This runs independently of TVMaze sync - it uses existing database shows
    and adds any that match selections but aren't already in Sonarr.
    """
    # 1. Get all TVDB IDs currently in Sonarr (ONE API call)
    sonarr_series = sonarr.get_all_series()
    existing_tvdb_ids = {s['tvdbId'] for s in sonarr_series if s.get('tvdbId')}
    logger.info(f"Found {len(existing_tvdb_ids)} shows in Sonarr")

    # 2. Iterate database shows with TVDB IDs and check against selections
    candidates = []
    total_checked = 0

    for show in db.get_all_shows_with_tvdb():
        total_checked += 1

        # Skip if already in Sonarr
        if show.tvdb_id in existing_tvdb_ids:
            continue

        # Check if show matches selections
        result = processor.process(show)
        if result.decision == Decision.ADD:
            candidates.append((show, result))

    logger.info(f"Checked {total_checked} shows, found {len(candidates)} matching selections not in Sonarr")

    if not candidates:
        return

    # 3. Add candidates to Sonarr
    added = 0
    failed = 0

    for show, result in candidates:
        if config.dry_run:
            logger.info(f"[DRY RUN] Would add: {show.title} (matched: {result.reason})")
            added += 1
            continue

        # Lookup and add to Sonarr
        series_data = sonarr.lookup_series(show.tvdb_id)
        if not series_data:
            logger.warning(f"Cannot find {show.title} in Sonarr lookup")
            failed += 1
            continue

        add_result = sonarr.add_series(result.sonarr_params, series_data)

        if add_result.success:
            db.mark_show_added(show.tvmaze_id, add_result.series_id)
            logger.info(f"Added: {show.title}")
            added += 1
        elif add_result.exists:
            db.update_show_status(show.tvmaze_id, ProcessingStatus.EXISTS)
            added += 1  # Count as success since it's in Sonarr
        else:
            db.mark_show_failed(show.tvmaze_id, add_result.error)
            logger.warning(f"Failed to add {show.title}: {add_result.error}")
            failed += 1

    logger.info(f"Selections sync complete: {added} added, {failed} failed")


def main():
    """Application entry point."""

    # ============ Load Configuration ============
    config_path = Path(os.environ.get('CONFIG_PATH', '/config/config.yaml'))
    try:
        config = load_config(config_path)
    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
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

    # ============ Sync Selections to Sonarr ============
    # Ensure all shows matching selections are in Sonarr (independent of TVMaze sync)
    sync_selections_to_sonarr(db, config, sonarr, processor)

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

    # ============ Start Scheduler ============
    interval = parse_duration(config.sync.poll_interval)
    scheduler = Scheduler(interval=interval, sync_func=run_sync)

    # ============ Start Flask Server ============
    app = None
    if config.server.enabled:
        from .server import create_app
        app = create_app(db, state, scheduler, sonarr, processor, config)
        flask_thread = threading.Thread(
            target=lambda: app.run(
                host='0.0.0.0',
                port=config.server.port,
                threaded=True,
                use_reloader=False
            )
        )
        flask_thread.daemon = True
        flask_thread.start()
        logger.info(f"HTTP server listening on port {config.server.port}")

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
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)


def sync_cycle(
    db: Database,
    state: SyncState,
    config: Config,
    sonarr: SonarrClient,
    tvmaze: TVMazeClient,
    processor: ShowProcessor
) -> None:
    """Execute a single sync cycle."""

    stats = SyncStats(started_at=datetime.now(UTC))
    storage_path = Path(config.storage.path)

    try:
        if state.last_full_sync is None:
            # Initial full sync
            run_initial_sync(db, state, config, sonarr, tvmaze, processor, stats)
            state.last_full_sync = datetime.now(UTC)
            sync_initial_complete.set(1)
        else:
            # Incremental sync
            run_incremental_sync(db, state, config, sonarr, tvmaze, processor, stats)

        # Retry pending_tvdb shows
        retry_pending_tvdb(db, state, config, sonarr, tvmaze, processor, stats)

        # Update state
        state.last_incremental_sync = datetime.now(UTC)
        state.save(storage_path / "state.json")
        state.backup(storage_path / "state.json")

        stats.completed_at = datetime.now(UTC)
        record_sync_complete(stats, success=True)

        logger.info(
            f"Sync complete: {stats.shows_added} added, "
            f"{stats.shows_filtered} filtered, "
            f"{stats.shows_exists} already existed, "
            f"{stats.shows_skipped} skipped"
        )

    except Exception as e:
        logger.exception("Sync cycle failed")
        stats.completed_at = datetime.now(UTC)
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
                logger.info(f"Reached end of TVMaze index at page {page}")
                break  # End of pages

            logger.info(f"Processing page {page} ({len(shows_data)} shows)")

            for show_data in shows_data:
                try:
                    show = Show.from_tvmaze_response(show_data)
                    process_single_show(db, config, sonarr, processor, show, stats)
                    state.highest_tvmaze_id = max(state.highest_tvmaze_id, show.tvmaze_id)
                except Exception as e:
                    logger.error(f"Error processing show {show_data.get('id')}: {e}")
                    continue

            # Checkpoint progress
            state.last_tvmaze_page = page
            state.save(Path(config.storage.path) / "state.json")

            page += 1

        except TVMazeRateLimitError:
            logger.warning("Rate limited, backing off...")
            time.sleep(10)
            continue

    logger.info(f"Initial sync complete, processed {stats.shows_processed} shows")


def run_incremental_sync(db, state, config, sonarr, tvmaze, processor, stats):
    """Check for updated shows since last sync."""
    logger.info("Starting incremental sync...")

    try:
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
                except Exception as e:
                    logger.error(f"Error processing show {tvmaze_id}: {e}")

        # Check for new shows beyond highest known ID
        check_for_new_shows(db, state, config, sonarr, tvmaze, processor, stats)

    except Exception as e:
        logger.error(f"Incremental sync error: {e}")
        raise


def check_for_new_shows(db, state, config, sonarr, tvmaze, processor, stats):
    """Check for shows with IDs higher than highest known."""
    # Try fetching shows incrementally above highest known ID
    current_id = state.highest_tvmaze_id + 1
    consecutive_not_found = 0
    max_not_found = 10  # Stop after 10 consecutive 404s

    logger.info(f"Checking for new shows above ID {state.highest_tvmaze_id}")

    while consecutive_not_found < max_not_found:
        try:
            show_data = tvmaze.get_show(current_id)
            show = Show.from_tvmaze_response(show_data)
            process_single_show(db, config, sonarr, processor, show, stats)
            state.highest_tvmaze_id = max(state.highest_tvmaze_id, current_id)
            consecutive_not_found = 0
            current_id += 1
        except TVMazeNotFoundError:
            consecutive_not_found += 1
            current_id += 1
        except TVMazeRateLimitError:
            logger.warning("Rate limited, backing off...")
            time.sleep(10)
        except Exception as e:
            logger.error(f"Error checking show {current_id}: {e}")
            consecutive_not_found += 1
            current_id += 1

    logger.info(f"New show check complete. Highest ID: {state.highest_tvmaze_id}")


def retry_pending_tvdb(db, state, config, sonarr, tvmaze, processor, stats):
    """Retry shows pending TVDB ID."""
    now = datetime.now(UTC)
    abandon_after = parse_duration(config.sync.abandon_after)

    # First, mark shows that have exceeded abandon_after as failed
    shows_to_abandon = db.get_shows_to_abandon(now, abandon_after)
    for show in shows_to_abandon:
        logger.warning(
            f"Show {show.title} exceeded abandon_after ({config.sync.abandon_after}), marking as failed"
        )
        db.mark_show_failed(show.tvmaze_id, f"No TVDB ID after {config.sync.abandon_after}")

    # Then get shows ready for retry
    shows_to_retry = db.get_shows_for_retry(now, abandon_after)

    if not shows_to_retry:
        return

    logger.info(f"Retrying {len(shows_to_retry)} shows pending TVDB ID")

    for show in shows_to_retry:
        try:
            # Re-fetch show data from TVMaze
            show_data = tvmaze.get_show(show.tvmaze_id)
            updated_show = Show.from_tvmaze_response(show_data)

            # Preserve pending_since and retry_count from original show
            updated_show.pending_since = show.pending_since
            updated_show.retry_count = show.retry_count
            updated_show.last_checked = now
            db.upsert_show(updated_show)

            # Process again
            if updated_show.tvdb_id:
                logger.info(f"Show {show.title} now has TVDB ID, processing")
                db.increment_retry_count(show.tvmaze_id)
                process_single_show(db, config, sonarr, processor, updated_show, stats)
            else:
                # Still no TVDB ID - schedule next retry
                db.increment_retry_count(show.tvmaze_id)
                retry_after = now + parse_duration(config.sync.retry_delay)
                db.mark_show_pending_tvdb(show.tvmaze_id, retry_after, now)

        except TVMazeNotFoundError:
            logger.warning(f"Show {show.tvmaze_id} no longer exists on TVMaze")
            db.mark_show_failed(show.tvmaze_id, "Removed from TVMaze")
        except Exception as e:
            logger.error(f"Error retrying show {show.title}: {e}")


def process_single_show(db, config, sonarr, processor, show, stats):
    """Process a single show through filters and Sonarr."""
    stats.shows_processed += 1

    # Store show in database
    show.last_checked = datetime.now(UTC)
    db.upsert_show(show)

    # Process through filters
    result = processor.process(show)

    if result.decision == Decision.FILTER:
        db.mark_show_filtered(show.tvmaze_id, result.reason, result.filter_category)
        stats.shows_filtered += 1
        if config.dry_run:
            logger.info(f"[DRY RUN] Filtered: {show.title} - {result.reason}")

    elif result.decision == Decision.RETRY:
        retry_after = datetime.now(UTC) + parse_duration(config.sync.retry_delay)
        db.mark_show_pending_tvdb(show.tvmaze_id, retry_after)
        stats.shows_skipped += 1
        if config.dry_run:
            logger.info(f"[DRY RUN] Pending TVDB: {show.title}")

    elif result.decision == Decision.ADD:
        if config.dry_run:
            # In dry run, mark as "would add" but don't call Sonarr
            logger.info(f"[DRY RUN] Would add: {show.title} (matched: {result.reason})")
            stats.shows_added += 1
            return

        # Lookup and add to Sonarr
        series_data = sonarr.lookup_series(show.tvdb_id)
        if not series_data:
            logger.warning(f"Cannot find {show.title} in Sonarr, marking as pending TVDB")
            retry_after = datetime.now(UTC) + parse_duration(config.sync.retry_delay)
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
