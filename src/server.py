"""Flask HTTP server for health, metrics, and API."""

import logging

from flask import Flask, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .config import Config
from .database import Database
from .metrics import update_db_metrics
from .processor import ShowProcessor, re_evaluate_filtered_shows
from .state import SyncState

logger = logging.getLogger(__name__)


def create_app(
    db: Database,
    state: SyncState,
    scheduler: "Scheduler",
    sonarr_client: "SonarrClient",
    processor: ShowProcessor,
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
            "sonarr": sonarr_client.is_healthy(),
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
        """Get current operational state summary."""
        return jsonify({
            "last_full_sync": state.last_full_sync.isoformat() if state.last_full_sync else None,
            "last_incremental_sync": state.last_incremental_sync.isoformat() if state.last_incremental_sync else None,
            "highest_tvmaze_id": state.highest_tvmaze_id,
            "next_scheduled_run": scheduler.next_run.isoformat() if scheduler.next_run else None,
            "sync_running": scheduler.is_running,
            "status_counts": db.get_status_counts(),
            "total_shows": db.get_total_count(),
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

        if status:
            shows = db.get_shows_by_status(
                status=status,
                limit=min(limit, 1000),
                offset=offset
            )
        else:
            # If no status filter, limit results
            shows = []

        return jsonify({
            "shows": [s.to_dict() for s in shows],
            "count": len(shows),
            "limit": limit,
            "offset": offset
        })

    @app.route('/refilter', methods=['POST'])
    def refilter():
        """Force re-evaluation of all filtered shows."""
        try:
            count = re_evaluate_filtered_shows(db, processor)
            return jsonify({
                "status": "complete",
                "shows_re_evaluated": count
            })
        except Exception as e:
            logger.error(f"Refilter failed: {e}")
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500

    return app
