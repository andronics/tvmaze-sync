"""Tests for Flask HTTP server."""

import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from src.models import ProcessingStatus


def test_create_app(flask_app):
    """Test Flask app creation."""
    assert flask_app is not None
    assert flask_app.config['TESTING'] is True


def test_health_endpoint(flask_client):
    """Test /health endpoint."""
    response = flask_client.get('/health')

    assert response.status_code == 200
    assert response.json == {"status": "healthy"}


def test_ready_endpoint_healthy(flask_client, mock_flask_dependencies):
    """Test /ready endpoint when healthy."""
    # Mock dependencies are healthy by default
    response = flask_client.get('/ready')

    assert response.status_code == 200
    data = response.json
    assert data["status"] == "ready"
    assert data["database"] is True
    assert data["sonarr"] is True


def test_ready_endpoint_unhealthy_database(flask_client, mock_flask_dependencies):
    """Test /ready endpoint when database is unhealthy."""
    # Make database unhealthy
    mock_flask_dependencies['db'].is_healthy = Mock(return_value=False)

    response = flask_client.get('/ready')

    assert response.status_code == 503
    data = response.json
    assert data["status"] == "not ready"
    assert data["database"] is False


def test_ready_endpoint_unhealthy_sonarr(flask_client, mock_flask_dependencies):
    """Test /ready endpoint when Sonarr is unhealthy."""
    # Make Sonarr unhealthy
    mock_flask_dependencies['sonarr_client'].is_healthy.return_value = False

    response = flask_client.get('/ready')

    assert response.status_code == 503
    data = response.json
    assert data["status"] == "not ready"
    assert data["sonarr"] is False


def test_metrics_endpoint(flask_client):
    """Test /metrics endpoint."""
    response = flask_client.get('/metrics')

    assert response.status_code == 200
    assert response.content_type.startswith('text/plain')
    # Should contain Prometheus metrics
    assert b'tvmaze_' in response.data


def test_metrics_content_type(flask_client):
    """Test /metrics returns correct content type."""
    response = flask_client.get('/metrics')

    assert 'text/plain' in response.content_type
    assert 'version=0.0.4' in response.content_type


def test_trigger_endpoint_success(flask_client, mock_flask_dependencies):
    """Test /trigger endpoint when scheduler is not running."""
    scheduler = mock_flask_dependencies['scheduler']
    scheduler.is_running = False

    response = flask_client.post('/trigger')

    assert response.status_code == 200
    assert response.json == {"status": "triggered"}
    scheduler.trigger_now.assert_called_once()


def test_trigger_endpoint_already_running(flask_client, mock_flask_dependencies):
    """Test /trigger endpoint when scheduler is already running."""
    scheduler = mock_flask_dependencies['scheduler']
    scheduler.is_running = True

    response = flask_client.post('/trigger')

    assert response.status_code == 409
    data = response.json
    assert "already running" in data["error"].lower()
    scheduler.trigger_now.assert_not_called()


def test_state_endpoint(flask_client, mock_flask_dependencies):
    """Test /state endpoint."""
    state = mock_flask_dependencies['state']
    state.last_full_sync = datetime(2024, 1, 1, 12, 0, 0)
    state.last_incremental_sync = datetime(2024, 1, 2, 12, 0, 0)
    state.last_tvmaze_page = 100
    state.highest_tvmaze_id = 50000

    response = flask_client.get('/state')

    assert response.status_code == 200
    data = response.json
    assert 'last_full_sync' in data
    assert 'last_incremental_sync' in data
    assert data['last_tvmaze_page'] == 100
    assert data['highest_tvmaze_id'] == 50000


def test_shows_endpoint_with_status(flask_client, mock_flask_dependencies, sample_show):
    """Test /shows endpoint with status filter."""
    db = mock_flask_dependencies['db']

    # Insert a test show
    db.upsert_show(sample_show)
    db.mark_show_added(sample_show.tvmaze_id, sonarr_series_id=1)

    response = flask_client.get('/shows?status=added')

    assert response.status_code == 200
    data = response.json
    assert isinstance(data, list)
    assert len(data) >= 1


def test_shows_endpoint_with_pagination(flask_client, mock_flask_dependencies, sample_show):
    """Test /shows endpoint with limit and offset."""
    db = mock_flask_dependencies['db']

    # Insert multiple shows
    for i in range(5):
        show = sample_show
        show.tvmaze_id = i + 1
        db.upsert_show(show)
        db.mark_show_added(show.tvmaze_id, sonarr_series_id=i + 1)

    response = flask_client.get('/shows?status=added&limit=2&offset=1')

    assert response.status_code == 200
    data = response.json
    assert isinstance(data, list)
    assert len(data) <= 2


def test_shows_endpoint_no_status_filter(flask_client):
    """Test /shows endpoint without status filter."""
    response = flask_client.get('/shows')

    assert response.status_code == 200
    data = response.json
    assert isinstance(data, list)


def test_refilter_endpoint_success(flask_client, mock_flask_dependencies, sample_show):
    """Test /refilter endpoint success."""
    db = mock_flask_dependencies['db']
    processor = mock_flask_dependencies['processor']

    # Insert a filtered show
    db.upsert_show(sample_show)
    db.mark_show_filtered(sample_show.tvmaze_id, "Genre excluded", "genre")

    response = flask_client.post('/refilter')

    assert response.status_code == 200
    data = response.json
    assert 'refiltered' in data
    assert isinstance(data['refiltered'], int)


def test_refilter_endpoint_error(flask_client, mock_flask_dependencies, monkeypatch):
    """Test /refilter endpoint error handling."""
    # Make re_evaluate_filtered_shows raise an error
    def mock_refilter_error(*args, **kwargs):
        raise Exception("Test error")

    monkeypatch.setattr('src.server.re_evaluate_filtered_shows', mock_refilter_error)

    response = flask_client.post('/refilter')

    assert response.status_code == 500
    data = response.json
    assert data['status'] == 'error'
    assert 'error' in data
