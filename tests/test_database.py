"""Tests for database module."""

import pytest
from datetime import datetime

from src.models import ProcessingStatus, Show


@pytest.mark.unit
def test_database_upsert_and_get(test_db, sample_show):
    """Test upserting and retrieving a show."""
    test_db.upsert_show(sample_show)

    retrieved = test_db.get_show(sample_show.tvmaze_id)

    assert retrieved is not None
    assert retrieved.tvmaze_id == sample_show.tvmaze_id
    assert retrieved.title == sample_show.title
    assert retrieved.tvdb_id == sample_show.tvdb_id


@pytest.mark.unit
def test_database_get_nonexistent_show(test_db):
    """Test getting a show that doesn't exist."""
    show = test_db.get_show(99999)
    assert show is None


@pytest.mark.unit
def test_database_get_show_by_tvdb(test_db, sample_show):
    """Test getting show by TVDB ID."""
    test_db.upsert_show(sample_show)

    retrieved = test_db.get_show_by_tvdb(sample_show.tvdb_id)

    assert retrieved is not None
    assert retrieved.tvdb_id == sample_show.tvdb_id


@pytest.mark.unit
def test_database_delete_show(test_db, sample_show):
    """Test deleting a show."""
    test_db.upsert_show(sample_show)

    deleted = test_db.delete_show(sample_show.tvmaze_id)
    assert deleted is True

    retrieved = test_db.get_show(sample_show.tvmaze_id)
    assert retrieved is None


@pytest.mark.unit
def test_database_get_status_counts(test_db, sample_show):
    """Test getting status counts."""
    sample_show.processing_status = ProcessingStatus.ADDED
    test_db.upsert_show(sample_show)

    show2 = Show(
        tvmaze_id=2,
        title="Show 2",
        processing_status=ProcessingStatus.FILTERED,
        last_checked=datetime.utcnow()
    )
    test_db.upsert_show(show2)

    counts = test_db.get_status_counts()

    assert counts.get(ProcessingStatus.ADDED) == 1
    assert counts.get(ProcessingStatus.FILTERED) == 1


@pytest.mark.unit
def test_database_mark_show_added(test_db, sample_show):
    """Test marking show as added."""
    test_db.upsert_show(sample_show)

    test_db.mark_show_added(sample_show.tvmaze_id, sonarr_series_id=123)

    retrieved = test_db.get_show(sample_show.tvmaze_id)
    assert retrieved.processing_status == ProcessingStatus.ADDED
    assert retrieved.sonarr_series_id == 123


@pytest.mark.unit
def test_database_mark_show_filtered(test_db, sample_show):
    """Test marking show as filtered."""
    test_db.upsert_show(sample_show)

    test_db.mark_show_filtered(
        sample_show.tvmaze_id,
        reason="Excluded genre: Reality",
        category="genre"
    )

    retrieved = test_db.get_show(sample_show.tvmaze_id)
    assert retrieved.processing_status == ProcessingStatus.FILTERED
    assert "Reality" in retrieved.filter_reason


@pytest.mark.unit
def test_database_get_highest_tvmaze_id(test_db):
    """Test getting highest TVMaze ID."""
    show1 = Show(tvmaze_id=100, title="Show 1", last_checked=datetime.utcnow())
    show2 = Show(tvmaze_id=200, title="Show 2", last_checked=datetime.utcnow())
    show3 = Show(tvmaze_id=150, title="Show 3", last_checked=datetime.utcnow())

    test_db.upsert_show(show1)
    test_db.upsert_show(show2)
    test_db.upsert_show(show3)

    highest = test_db.get_highest_tvmaze_id()
    assert highest == 200


@pytest.mark.unit
def test_database_get_total_count(test_db):
    """Test getting total show count."""
    show1 = Show(tvmaze_id=1, title="Show 1", last_checked=datetime.utcnow())
    show2 = Show(tvmaze_id=2, title="Show 2", last_checked=datetime.utcnow())

    test_db.upsert_show(show1)
    test_db.upsert_show(show2)

    count = test_db.get_total_count()
    assert count == 2


@pytest.mark.unit
def test_database_get_shows_by_status(test_db):
    """Test getting shows by status."""
    show1 = Show(
        tvmaze_id=1,
        title="Show 1",
        processing_status=ProcessingStatus.FILTERED,
        last_checked=datetime.utcnow()
    )
    show2 = Show(
        tvmaze_id=2,
        title="Show 2",
        processing_status=ProcessingStatus.FILTERED,
        last_checked=datetime.utcnow()
    )
    show3 = Show(
        tvmaze_id=3,
        title="Show 3",
        processing_status=ProcessingStatus.ADDED,
        last_checked=datetime.utcnow()
    )

    test_db.upsert_show(show1)
    test_db.upsert_show(show2)
    test_db.upsert_show(show3)

    filtered_shows = test_db.get_shows_by_status(ProcessingStatus.FILTERED)
    assert len(filtered_shows) == 2

    added_shows = test_db.get_shows_by_status(ProcessingStatus.ADDED)
    assert len(added_shows) == 1


@pytest.mark.unit
def test_database_is_healthy(test_db):
    """Test database health check."""
    assert test_db.is_healthy() is True
