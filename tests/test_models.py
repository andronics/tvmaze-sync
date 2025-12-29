"""Tests for models module."""

import pytest
from datetime import date, datetime

from src.models import Decision, ProcessingResult, ProcessingStatus, Show, SyncStats


@pytest.mark.unit
def test_show_from_tvmaze_response(tvmaze_show_response):
    """Test Show.from_tvmaze_response()."""
    show = Show.from_tvmaze_response(tvmaze_show_response)

    assert show.tvmaze_id == 1
    assert show.title == "Breaking Bad"
    assert show.tvdb_id == 81189
    assert show.imdb_id == "tt0903747"
    assert show.language == "English"
    assert show.country == "US"
    assert show.type == "Scripted"
    assert show.status == "Ended"
    assert show.premiered == date(2008, 1, 20)
    assert show.ended == date(2013, 9, 29)
    assert show.network == "AMC"
    assert show.genres == ["Drama", "Crime", "Thriller"]
    assert show.runtime == 47
    assert show.tvmaze_updated_at == 1704067200


@pytest.mark.unit
def test_show_to_db_dict(sample_show):
    """Test Show.to_db_dict()."""
    data = sample_show.to_db_dict()

    assert data["tvmaze_id"] == 1
    assert data["tvdb_id"] == 12345
    assert data["title"] == "Breaking Bad"
    assert data["language"] == "English"
    assert data["country"] == "US"
    assert data["genres"] is not None
    assert "Drama" in data["genres"]


@pytest.mark.unit
def test_show_to_dict(sample_show):
    """Test Show.to_dict()."""
    data = sample_show.to_dict()

    assert data["tvmaze_id"] == 1
    assert data["title"] == "Breaking Bad"
    assert isinstance(data["genres"], list)


@pytest.mark.unit
def test_processing_result():
    """Test ProcessingResult creation."""
    result = ProcessingResult(
        decision=Decision.FILTER,
        reason="Excluded genre: Reality",
        filter_category="genre"
    )

    assert result.decision == Decision.FILTER
    assert "Reality" in result.reason
    assert result.filter_category == "genre"


@pytest.mark.unit
def test_sync_stats_duration():
    """Test SyncStats duration calculation."""
    started = datetime(2024, 1, 1, 10, 0, 0)
    completed = datetime(2024, 1, 1, 10, 5, 30)

    stats = SyncStats(started_at=started, completed_at=completed)

    assert stats.duration_seconds == 330.0  # 5.5 minutes


@pytest.mark.unit
def test_processing_status_values():
    """Test ProcessingStatus constants."""
    assert ProcessingStatus.PENDING == "pending"
    assert ProcessingStatus.FILTERED == "filtered"
    assert ProcessingStatus.ADDED == "added"
    assert ProcessingStatus.EXISTS == "exists"
    assert ProcessingStatus.FAILED == "failed"
