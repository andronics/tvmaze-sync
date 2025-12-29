"""Prometheus metric definitions."""

import logging

from prometheus_client import Counter, Gauge

from .database import Database
from .models import SyncStats

logger = logging.getLogger(__name__)

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
    try:
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

    except Exception as e:
        logger.error(f"Failed to update database metrics: {e}")


def record_sync_complete(stats: SyncStats, success: bool) -> None:
    """Record metrics after sync completion."""
    try:
        if stats.completed_at:
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
        if stats.shows_added > 0:
            shows_processed_total.labels(result='added').inc(stats.shows_added)
        if stats.shows_filtered > 0:
            shows_processed_total.labels(result='filtered').inc(stats.shows_filtered)
        if stats.shows_skipped > 0:
            shows_processed_total.labels(result='skipped').inc(stats.shows_skipped)
        if stats.shows_failed > 0:
            shows_processed_total.labels(result='failed').inc(stats.shows_failed)
        if stats.shows_exists > 0:
            shows_processed_total.labels(result='exists').inc(stats.shows_exists)

    except Exception as e:
        logger.error(f"Failed to record sync metrics: {e}")
