"""Flask HTTP server for health, metrics, API, and web UI."""

import logging
from datetime import datetime, UTC
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .config import Config
from .database import Database
from .metrics import update_db_metrics
from .processor import ShowProcessor, re_evaluate_filtered_shows
from .state import SyncState

logger = logging.getLogger(__name__)


def mask_sensitive_values(config_dict: dict, mask: str = "***") -> dict:
    """Mask sensitive configuration values for display."""
    sensitive_keys = {'api_key', 'password', 'secret', 'token'}

    def _mask_recursive(obj):
        if isinstance(obj, dict):
            return {
                k: mask if any(s in k.lower() for s in sensitive_keys) else _mask_recursive(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [_mask_recursive(item) for item in obj]
        return obj

    return _mask_recursive(config_dict)


def create_app(
    db: Database,
    state: SyncState,
    scheduler: "Scheduler",
    sonarr_client: "SonarrClient",
    processor: ShowProcessor,
    config: Config
) -> Flask:
    """Create Flask application."""

    # Get the directory where server.py is located
    src_dir = Path(__file__).parent

    app = Flask(
        __name__,
        template_folder=str(src_dir / 'templates'),
        static_folder=str(src_dir / 'static'),
        static_url_path='/static'
    )
    app.secret_key = config.server.api_key  # For flash messages

    # ============ Template Filters ============

    @app.template_filter('format_datetime')
    def format_datetime_filter(value):
        """Format datetime for display."""
        if value is None:
            return "Never"
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return value
        return value.strftime("%Y-%m-%d %H:%M:%S UTC")

    @app.template_filter('format_number')
    def format_number_filter(value):
        """Format number with thousands separator."""
        if value is None:
            return "0"
        return f"{value:,}"

    @app.template_filter('status_color')
    def status_color_filter(status: str) -> str:
        """Return Tailwind color class for processing status."""
        colors = {
            'added': 'green',
            'filtered': 'gray',
            'pending_tvdb': 'yellow',
            'pending': 'blue',
            'failed': 'red',
            'exists': 'purple',
            'skipped': 'orange',
            'abandoned': 'gray'
        }
        return colors.get(status, 'gray')

    # ============ Context Processors ============

    @app.context_processor
    def inject_navigation():
        """Inject navigation data into all templates."""
        nav_items = [
            {'url': '/', 'name': 'Dashboard'},
            {'url': '/ui/shows', 'name': 'Shows'},
            {'url': '/ui/config', 'name': 'Config'},
            {'url': '/ui/api', 'name': 'API Docs'},
            {'url': '/ui/about', 'name': 'About'},
        ]
        return {
            'nav_items': nav_items,
            'current_path': request.path,
            'sync_running': scheduler.is_running,
            'now': datetime.now
        }

    @app.context_processor
    def inject_api_key():
        """Inject API key for authenticated requests from templates."""
        api_key = (
            request.headers.get('X-API-Key') or
            request.args.get('api_key') or
            request.cookies.get('api_key')
        )
        return {'api_key': api_key or ''}

    # ============ Authentication ============

    @app.before_request
    def check_api_key():
        """Validate API key for protected endpoints."""
        # Public endpoints - no auth required
        public_paths = ['/health', '/ready', '/metrics', '/login']
        if request.path in public_paths or request.path.startswith('/static/'):
            return

        # Check header first, then query param, then cookie
        api_key = (
            request.headers.get('X-API-Key') or
            request.args.get('api_key') or
            request.cookies.get('api_key')
        )

        if not api_key or api_key != config.server.api_key:
            # For web UI routes, redirect to login
            if request.path == '/' or request.path.startswith('/ui/'):
                return redirect(url_for('ui_login', next=request.url))
            # For API routes, return JSON error
            return jsonify({"error": "Unauthorized"}), 401

    # ============ Login/Logout Routes ============

    @app.route('/login', methods=['GET', 'POST'])
    def ui_login():
        """Handle login for web UI."""
        if request.method == 'POST':
            api_key = request.form.get('api_key')
            if api_key == config.server.api_key:
                next_url = request.args.get('next', url_for('ui_dashboard'))
                response = redirect(next_url)
                response.set_cookie(
                    'api_key',
                    api_key,
                    httponly=True,
                    secure=request.is_secure,
                    samesite='Lax',
                    max_age=86400 * 7  # 7 days
                )
                return response
            else:
                return render_template('login.html', error="Invalid API key")

        return render_template('login.html')

    @app.route('/logout')
    def ui_logout():
        """Handle logout for web UI."""
        response = redirect(url_for('ui_login'))
        response.delete_cookie('api_key')
        return response

    # ============ Web UI Routes ============

    @app.route('/')
    def ui_dashboard():
        """Render dashboard page."""
        status_counts = db.get_status_counts()
        total_shows = db.get_total_count()
        filter_reasons = db.get_filter_reason_counts()

        return render_template(
            'dashboard.html',
            state=state,
            scheduler=scheduler,
            status_counts=status_counts,
            total_shows=total_shows,
            filter_reasons=filter_reasons,
            db_healthy=db.is_healthy(),
            sonarr_healthy=sonarr_client.is_healthy()
        )

    @app.route('/ui/shows')
    def ui_shows():
        """Render shows browser page."""
        return render_template('shows.html')

    @app.route('/ui/config')
    def ui_config():
        """Render configuration viewer page."""
        config_dict = config.to_dict()
        masked_config = mask_sensitive_values(config_dict)
        return render_template('config.html', config=masked_config)

    @app.route('/ui/api')
    def ui_api():
        """Render API documentation page."""
        return render_template('api.html')

    @app.route('/ui/about')
    def ui_about():
        """Render about page."""
        return render_template('about.html')

    # ============ HTMX Partial Routes ============

    @app.route('/ui/partials/nav-status')
    def ui_partial_nav_status():
        """Return nav sync status HTML partial for HTMX polling."""
        return render_template(
            'partials/nav_status.html',
            sync_running=scheduler.is_running
        )

    @app.route('/ui/partials/sync-status')
    def ui_partial_sync_status():
        """Return sync status HTML partial for HTMX polling."""
        status_counts = db.get_status_counts()
        return render_template(
            'partials/sync_status.html',
            state=state,
            scheduler=scheduler,
            sync_running=scheduler.is_running,
            db_healthy=db.is_healthy(),
            sonarr_healthy=sonarr_client.is_healthy(),
            status_counts=status_counts,
            total_shows=db.get_total_count()
        )

    @app.route('/ui/partials/shows')
    def ui_partial_shows():
        """Return shows table HTML partial for HTMX filtering."""
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        # Use the new search method if available, otherwise fall back
        shows = db.search_shows(
            status=status,
            search=search,
            limit=min(limit, 100),
            offset=offset
        )

        total = db.count_shows(status=status, search=search)

        return render_template(
            'partials/shows_table.html',
            shows=shows,
            total=total,
            limit=limit,
            offset=offset,
            status=status,
            search=search
        )

    @app.route('/ui/partials/show/<int:tvmaze_id>')
    def ui_partial_show_detail(tvmaze_id: int):
        """Return show detail HTML partial for modal."""
        show = db.get_show(tvmaze_id)
        if not show:
            return "Show not found", 404
        return render_template('partials/show_detail.html', show=show)

    # ============ Error Handlers ============

    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors."""
        if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
            return jsonify({"error": "Not found"}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        logger.error(f"Internal server error: {error}")
        if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
            return jsonify({"error": "Internal server error"}), 500
        return render_template('errors/500.html'), 500

    # ============ Observability Endpoints (Public) ============

    @app.route('/health')
    def health():
        """Liveness probe."""
        return jsonify({"status": "healthy"})

    @app.route('/ready')
    def ready():
        """
        Readiness probe.

        Checks:
        - Database accessible
        - Sonarr reachable
        """
        database_healthy = db.is_healthy()
        sonarr_healthy = sonarr_client.is_healthy()

        all_healthy = database_healthy and sonarr_healthy
        status_code = 200 if all_healthy else 503

        return jsonify({
            "status": "ready" if all_healthy else "not ready",
            "database": database_healthy,
            "sonarr": sonarr_healthy
        }), status_code

    @app.route('/metrics')
    def metrics():
        """Prometheus metrics endpoint."""
        update_db_metrics(db)
        return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

    # ============ API Endpoints (Protected) ============

    @app.route('/trigger', methods=['POST'])
    def trigger():
        """Manually trigger sync cycle."""
        if scheduler.is_running:
            return jsonify({
                "status": "already_running",
                "error": "Already running - sync cycle in progress"
            }), 409

        scheduler.trigger_now()
        return jsonify({"status": "triggered"})

    @app.route('/state')
    def get_state():
        """Get current operational state summary."""
        return jsonify({
            "last_full_sync": state.last_full_sync.isoformat() if state.last_full_sync else None,
            "last_incremental_sync": state.last_incremental_sync.isoformat() if state.last_incremental_sync else None,
            "last_tvmaze_page": state.last_tvmaze_page,
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

        return jsonify([s.to_dict() for s in shows])

    @app.route('/refilter', methods=['POST'])
    def refilter():
        """Force re-evaluation of all filtered shows."""
        try:
            count = re_evaluate_filtered_shows(db, processor)
            return jsonify({
                "status": "complete",
                "refiltered": count
            })
        except Exception as e:
            logger.error(f"Refilter failed: {e}")
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500

    @app.route('/config')
    def get_config():
        """Return the complete running configuration."""
        return jsonify(config.to_dict())

    return app
