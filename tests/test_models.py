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


# Additional tests for comprehensive coverage


@pytest.mark.unit
def test_show_from_db_row():
    """Test Show.from_db_row() parsing."""
    import sqlite3

    # Create mock database row
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE shows (
            tvmaze_id INTEGER,
            tvdb_id INTEGER,
            imdb_id TEXT,
            title TEXT,
            language TEXT,
            country TEXT,
            type TEXT,
            status TEXT,
            premiered TEXT,
            ended TEXT,
            network TEXT,
            web_channel TEXT,
            genres TEXT,
            runtime INTEGER,
            processing_status TEXT,
            filter_reason TEXT,
            filter_category TEXT,
            sonarr_series_id INTEGER,
            added_to_sonarr_at TEXT,
            last_checked TEXT,
            tvmaze_updated_at INTEGER,
            retry_after TEXT,
            retry_count INTEGER,
            pending_since TEXT,
            error_message TEXT
        )
    """)

    cursor.execute("""
        INSERT INTO shows VALUES (
            1, 12345, 'tt0903747', 'Breaking Bad', 'English', 'US',
            'Scripted', 'Ended', '2008-01-20', '2013-09-29', 'AMC', NULL,
            '["Drama", "Crime"]', 47, 'pending', NULL, NULL, NULL, NULL,
            '2024-01-01T10:00:00', 1704067200, NULL, 0, NULL, NULL
        )
    """)

    cursor.execute("SELECT * FROM shows")
    row = cursor.fetchone()

    show = Show.from_db_row(row)

    assert show.tvmaze_id == 1
    assert show.tvdb_id == 12345
    assert show.imdb_id == "tt0903747"
    assert show.title == "Breaking Bad"
    assert show.language == "English"
    assert show.country == "US"
    assert show.type == "Scripted"
    assert show.status == "Ended"
    assert show.premiered == date(2008, 1, 20)
    assert show.ended == date(2013, 9, 29)
    assert show.network == "AMC"
    assert show.web_channel is None
    assert show.genres == ["Drama", "Crime"]
    assert show.runtime == 47
    assert show.processing_status == "pending"
    assert show.retry_count == 0

    conn.close()


@pytest.mark.unit
def test_show_from_db_row_with_null_fields():
    """Test Show.from_db_row() with NULL/missing fields."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE shows (
            tvmaze_id INTEGER,
            tvdb_id INTEGER,
            imdb_id TEXT,
            title TEXT,
            language TEXT,
            country TEXT,
            type TEXT,
            status TEXT,
            premiered TEXT,
            ended TEXT,
            network TEXT,
            web_channel TEXT,
            genres TEXT,
            runtime INTEGER,
            processing_status TEXT,
            filter_reason TEXT,
            filter_category TEXT,
            sonarr_series_id INTEGER,
            added_to_sonarr_at TEXT,
            last_checked TEXT,
            tvmaze_updated_at INTEGER,
            retry_after TEXT,
            retry_count INTEGER,
            pending_since TEXT,
            error_message TEXT
        )
    """)

    cursor.execute("""
        INSERT INTO shows VALUES (
            99, NULL, NULL, 'Minimal Show', NULL, NULL,
            NULL, NULL, NULL, NULL, NULL, NULL,
            NULL, NULL, 'pending', NULL, NULL, NULL, NULL,
            NULL, NULL, NULL, 0, NULL, NULL
        )
    """)

    cursor.execute("SELECT * FROM shows")
    row = cursor.fetchone()

    show = Show.from_db_row(row)

    assert show.tvmaze_id == 99
    assert show.tvdb_id is None
    assert show.imdb_id is None
    assert show.title == "Minimal Show"
    assert show.language is None
    assert show.genres == []
    assert show.premiered is None
    assert show.retry_count == 0

    conn.close()


@pytest.mark.unit
def test_show_from_db_row_invalid_json_genres():
    """Test Show.from_db_row() handles invalid JSON in genres field."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE shows (
            tvmaze_id INTEGER,
            tvdb_id INTEGER,
            imdb_id TEXT,
            title TEXT,
            language TEXT,
            country TEXT,
            type TEXT,
            status TEXT,
            premiered TEXT,
            ended TEXT,
            network TEXT,
            web_channel TEXT,
            genres TEXT,
            runtime INTEGER,
            processing_status TEXT,
            filter_reason TEXT,
            filter_category TEXT,
            sonarr_series_id INTEGER,
            added_to_sonarr_at TEXT,
            last_checked TEXT,
            tvmaze_updated_at INTEGER,
            retry_after TEXT,
            retry_count INTEGER,
            pending_since TEXT,
            error_message TEXT
        )
    """)

    cursor.execute("""
        INSERT INTO shows VALUES (
            1, 12345, NULL, 'Test Show', 'English', 'US',
            'Scripted', 'Running', NULL, NULL, 'NBC', NULL,
            'invalid json [', 30, 'pending', NULL, NULL, NULL, NULL,
            NULL, NULL, NULL, 0, NULL, NULL
        )
    """)

    cursor.execute("SELECT * FROM shows")
    row = cursor.fetchone()

    show = Show.from_db_row(row)

    # Should gracefully handle invalid JSON and default to empty list
    assert show.genres == []

    conn.close()


@pytest.mark.unit
def test_show_from_db_row_invalid_dates():
    """Test Show.from_db_row() handles invalid date strings."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE shows (
            tvmaze_id INTEGER,
            tvdb_id INTEGER,
            imdb_id TEXT,
            title TEXT,
            language TEXT,
            country TEXT,
            type TEXT,
            status TEXT,
            premiered TEXT,
            ended TEXT,
            network TEXT,
            web_channel TEXT,
            genres TEXT,
            runtime INTEGER,
            processing_status TEXT,
            filter_reason TEXT,
            filter_category TEXT,
            sonarr_series_id INTEGER,
            added_to_sonarr_at TEXT,
            last_checked TEXT,
            tvmaze_updated_at INTEGER,
            retry_after TEXT,
            retry_count INTEGER,
            pending_since TEXT,
            error_message TEXT
        )
    """)

    cursor.execute("""
        INSERT INTO shows VALUES (
            1, 12345, NULL, 'Test Show', 'English', 'US',
            'Scripted', 'Running', 'invalid-date', 'also-invalid', 'NBC', NULL,
            NULL, 30, 'pending', NULL, NULL, NULL, 'bad-datetime',
            'also-bad-datetime', NULL, 'invalid-retry', 0, NULL, NULL
        )
    """)

    cursor.execute("SELECT * FROM shows")
    row = cursor.fetchone()

    show = Show.from_db_row(row)

    # Should gracefully handle invalid dates and default to None
    assert show.premiered is None
    assert show.ended is None
    assert show.last_checked is None
    assert show.added_to_sonarr_at is None
    assert show.retry_after is None

    conn.close()


@pytest.mark.unit
def test_show_from_tvmaze_response_with_web_channel():
    """Test Show.from_tvmaze_response() with WebChannel instead of network."""
    data = {
        "id": 123,
        "name": "Netflix Show",
        "type": "Scripted",
        "language": "English",
        "status": "Running",
        "premiered": "2020-05-01",
        "runtime": 50,
        "genres": ["Drama"],
        "network": None,
        "webChannel": {
            "name": "Netflix",
            "country": {"code": "US"}
        },
        "externals": {"thetvdb": 99999, "imdb": "tt1234567"},
        "updated": 1704067200
    }

    show = Show.from_tvmaze_response(data)

    assert show.tvmaze_id == 123
    assert show.title == "Netflix Show"
    assert show.network is None
    assert show.web_channel == "Netflix"
    assert show.country == "US"
    assert show.tvdb_id == 99999
    assert show.imdb_id == "tt1234567"


@pytest.mark.unit
def test_show_from_tvmaze_response_missing_externals():
    """Test Show.from_tvmaze_response() with missing TVDB/IMDB IDs."""
    data = {
        "id": 456,
        "name": "New Show",
        "type": "Scripted",
        "language": "English",
        "status": "Running",
        "runtime": 30,
        "genres": ["Comedy"],
        "network": {"name": "ABC", "country": {"code": "US"}},
        "externals": {},  # No TVDB or IMDB
        "updated": 1704067200
    }

    show = Show.from_tvmaze_response(data)

    assert show.tvmaze_id == 456
    assert show.title == "New Show"
    assert show.tvdb_id is None
    assert show.imdb_id is None
    assert show.network == "ABC"
    assert show.country == "US"


@pytest.mark.unit
def test_show_from_tvmaze_response_invalid_dates():
    """Test Show.from_tvmaze_response() handles invalid date formats."""
    data = {
        "id": 789,
        "name": "Bad Dates Show",
        "type": "Scripted",
        "language": "English",
        "status": "Running",
        "premiered": "invalid-date-format",
        "ended": "also-bad",
        "runtime": 45,
        "genres": ["Thriller"],
        "network": {"name": "HBO", "country": {"code": "US"}},
        "externals": {"thetvdb": 11111},
        "updated": 1704067200
    }

    show = Show.from_tvmaze_response(data)

    assert show.tvmaze_id == 789
    assert show.title == "Bad Dates Show"
    # Invalid dates should be parsed as None
    assert show.premiered is None
    assert show.ended is None


@pytest.mark.unit
def test_sonarr_params_creation():
    """Test SonarrParams dataclass creation."""
    from src.models import SonarrParams

    params = SonarrParams(
        tvdb_id=12345,
        title="Test Show",
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=2,
        monitor="all",
        search_on_add=True,
        tags=[10, 20, 30]
    )

    assert params.tvdb_id == 12345
    assert params.title == "Test Show"
    assert params.root_folder == "/tv"
    assert params.quality_profile_id == 1
    assert params.language_profile_id == 2
    assert params.monitor == "all"
    assert params.search_on_add is True
    assert params.tags == [10, 20, 30]


@pytest.mark.unit
def test_decision_enum_values():
    """Test Decision enum values."""
    assert Decision.ADD.value == "add"
    assert Decision.FILTER.value == "filter"
    assert Decision.SKIP.value == "skip"
    assert Decision.RETRY.value == "retry"

    # Test enum can be compared
    assert Decision.ADD != Decision.FILTER
    assert Decision.ADD == Decision.ADD


@pytest.mark.unit
def test_sync_stats_incomplete():
    """Test SyncStats duration calculation without completion."""
    started = datetime(2024, 1, 1, 10, 0, 0)

    stats = SyncStats(started_at=started)

    # Without completed_at, duration should be 0
    assert stats.duration_seconds == 0.0
    assert stats.shows_processed == 0
    assert stats.shows_added == 0
    assert stats.api_calls_tvmaze == 0
