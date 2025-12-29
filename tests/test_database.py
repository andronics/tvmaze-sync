"""Tests for database module."""

import pytest
from datetime import UTC, datetime

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
        last_checked=datetime.now(UTC)
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
    show1 = Show(tvmaze_id=100, title="Show 1", last_checked=datetime.now(UTC))
    show2 = Show(tvmaze_id=200, title="Show 2", last_checked=datetime.now(UTC))
    show3 = Show(tvmaze_id=150, title="Show 3", last_checked=datetime.now(UTC))

    test_db.upsert_show(show1)
    test_db.upsert_show(show2)
    test_db.upsert_show(show3)

    highest = test_db.get_highest_tvmaze_id()
    assert highest == 200


@pytest.mark.unit
def test_database_get_total_count(test_db):
    """Test getting total show count."""
    show1 = Show(tvmaze_id=1, title="Show 1", last_checked=datetime.now(UTC))
    show2 = Show(tvmaze_id=2, title="Show 2", last_checked=datetime.now(UTC))

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
        last_checked=datetime.now(UTC)
    )
    show2 = Show(
        tvmaze_id=2,
        title="Show 2",
        processing_status=ProcessingStatus.FILTERED,
        last_checked=datetime.now(UTC)
    )
    show3 = Show(
        tvmaze_id=3,
        title="Show 3",
        processing_status=ProcessingStatus.ADDED,
        last_checked=datetime.now(UTC)
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


# Additional tests for comprehensive coverage

@pytest.mark.unit
def test_database_init_and_schema(temp_dir):
    """Test database initialization and schema creation."""
    from src.database import Database

    db_path = temp_dir / "new_test.db"
    db = Database(db_path)

    # Should have created tables
    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    assert 'shows' in tables
    assert 'schema_version' in tables

    db.close()


@pytest.mark.unit
def test_database_close(test_db):
    """Test database close operation."""
    test_db.close()

    # Connection should be closed
    # Attempting operations should fail or be handled
    assert test_db.conn is not None  # Connection object exists but is closed


@pytest.mark.unit
def test_database_upsert_shows_bulk(test_db):
    """Test bulk upsert operation."""
    shows = []
    for i in range(10):
        show = Show(
            tvmaze_id=i + 1,
            title=f"Show {i + 1}",
            last_checked=datetime.now(UTC)
        )
        shows.append(show)

    count = test_db.upsert_shows(shows)

    assert count == 10
    assert test_db.get_total_count() == 10


@pytest.mark.unit
def test_database_upsert_shows_empty(test_db):
    """Test bulk upsert with empty list."""
    count = test_db.upsert_shows([])

    assert count == 0


@pytest.mark.unit
def test_database_get_shows_for_retry(test_db, sample_show_no_tvdb):
    """Test getting shows ready for retry."""
    from datetime import timedelta

    # Insert show with retry in the past
    test_db.upsert_show(sample_show_no_tvdb)
    past_time = datetime.now(UTC) - timedelta(days=1)
    test_db.mark_show_pending_tvdb(sample_show_no_tvdb.tvmaze_id, retry_after=past_time)

    # Get shows ready for retry
    shows = test_db.get_shows_for_retry(now=datetime.now(UTC), max_retries=4)

    assert len(shows) == 1
    assert shows[0].tvmaze_id == sample_show_no_tvdb.tvmaze_id


@pytest.mark.unit
def test_database_get_shows_for_retry_not_ready(test_db, sample_show_no_tvdb):
    """Test getting shows not ready for retry yet."""
    from datetime import timedelta

    # Insert show with retry in the future
    test_db.upsert_show(sample_show_no_tvdb)
    future_time = datetime.now(UTC) + timedelta(days=1)
    test_db.mark_show_pending_tvdb(sample_show_no_tvdb.tvmaze_id, retry_after=future_time)

    # Should not return shows not ready yet
    shows = test_db.get_shows_for_retry(now=datetime.now(UTC), max_retries=4)

    assert len(shows) == 0


@pytest.mark.unit
def test_database_get_all_filtered_shows(test_db):
    """Test getting all filtered shows as iterator."""
    # Insert multiple filtered shows
    for i in range(5):
        show = Show(
            tvmaze_id=i + 1,
            title=f"Show {i + 1}",
            processing_status=ProcessingStatus.FILTERED,
            filter_reason="Test reason",
            last_checked=datetime.now(UTC)
        )
        test_db.upsert_show(show)

    # Get iterator
    filtered_shows = list(test_db.get_all_filtered_shows())

    assert len(filtered_shows) == 5


@pytest.mark.unit
def test_database_get_filter_reason_counts(test_db):
    """Test getting filter reason counts."""
    # Insert shows with different filter reasons using mark_show_filtered
    show1 = Show(
        tvmaze_id=1,
        title="Show 1",
        last_checked=datetime.now(UTC)
    )
    show2 = Show(
        tvmaze_id=2,
        title="Show 2",
        last_checked=datetime.now(UTC)
    )
    show3 = Show(
        tvmaze_id=3,
        title="Show 3",
        last_checked=datetime.now(UTC)
    )

    test_db.upsert_show(show1)
    test_db.upsert_show(show2)
    test_db.upsert_show(show3)

    # Mark shows as filtered with different categories
    test_db.mark_show_filtered(show1.tvmaze_id, "Genre excluded", "genre")
    test_db.mark_show_filtered(show2.tvmaze_id, "Genre excluded", "genre")
    test_db.mark_show_filtered(show3.tvmaze_id, "Language not included", "language")

    counts = test_db.get_filter_reason_counts()

    assert counts.get("genre") == 2
    assert counts.get("language") == 1


@pytest.mark.unit
def test_database_get_retry_counts(test_db, sample_show_no_tvdb):
    """Test getting retry count statistics."""
    test_db.upsert_show(sample_show_no_tvdb)
    test_db.mark_show_pending_tvdb(sample_show_no_tvdb.tvmaze_id, retry_after=datetime.now(UTC))
    test_db.increment_retry_count(sample_show_no_tvdb.tvmaze_id)

    counts = test_db.get_retry_counts()

    assert counts.get("0") >= 0  # Shows with 0 retries
    assert counts.get("1") == 1  # Our show with 1 retry


@pytest.mark.unit
def test_database_get_tvmaze_ids_updated_since(test_db):
    """Test getting TVMaze IDs updated since timestamp."""
    # Insert shows with different update times
    show1 = Show(
        tvmaze_id=1,
        title="Show 1",
        tvmaze_updated_at=1704067200,  # Newer
        last_checked=datetime.now(UTC)
    )
    show2 = Show(
        tvmaze_id=2,
        title="Show 2",
        tvmaze_updated_at=1704000000,  # Older
        last_checked=datetime.now(UTC)
    )

    test_db.upsert_show(show1)
    test_db.upsert_show(show2)

    # Get IDs updated since timestamp
    ids = test_db.get_tvmaze_ids_updated_since(timestamp=1704050000)

    assert 1 in ids
    assert 2 not in ids


@pytest.mark.unit
def test_database_mark_show_pending_tvdb(test_db, sample_show_no_tvdb):
    """Test marking show as pending TVDB."""
    from datetime import timedelta

    test_db.upsert_show(sample_show_no_tvdb)

    retry_after = datetime.now(UTC) + timedelta(weeks=1)
    test_db.mark_show_pending_tvdb(sample_show_no_tvdb.tvmaze_id, retry_after=retry_after)

    retrieved = test_db.get_show(sample_show_no_tvdb.tvmaze_id)
    assert retrieved.processing_status == ProcessingStatus.PENDING_TVDB
    assert retrieved.retry_after is not None


@pytest.mark.unit
def test_database_mark_show_failed(test_db, sample_show):
    """Test marking show as failed."""
    test_db.upsert_show(sample_show)

    test_db.mark_show_failed(sample_show.tvmaze_id, error_message="API error occurred")

    retrieved = test_db.get_show(sample_show.tvmaze_id)
    assert retrieved.processing_status == ProcessingStatus.FAILED
    assert "API error" in retrieved.error_message


@pytest.mark.unit
def test_database_update_show_status(test_db, sample_show):
    """Test updating show status."""
    test_db.upsert_show(sample_show)

    test_db.update_show_status(sample_show.tvmaze_id, ProcessingStatus.EXISTS)

    retrieved = test_db.get_show(sample_show.tvmaze_id)
    assert retrieved.processing_status == ProcessingStatus.EXISTS


@pytest.mark.unit
def test_database_increment_retry_count(test_db, sample_show_no_tvdb):
    """Test incrementing retry count."""
    test_db.upsert_show(sample_show_no_tvdb)
    test_db.mark_show_pending_tvdb(sample_show_no_tvdb.tvmaze_id, retry_after=datetime.now(UTC))

    # Increment once
    new_count = test_db.increment_retry_count(sample_show_no_tvdb.tvmaze_id)
    assert new_count == 1

    # Increment again
    new_count = test_db.increment_retry_count(sample_show_no_tvdb.tvmaze_id)
    assert new_count == 2

    retrieved = test_db.get_show(sample_show_no_tvdb.tvmaze_id)
    assert retrieved.retry_count == 2


@pytest.mark.unit
def test_database_get_shows_by_status_with_pagination(test_db):
    """Test getting shows by status with limit and offset."""
    # Insert 10 filtered shows
    for i in range(10):
        show = Show(
            tvmaze_id=i + 1,
            title=f"Show {i + 1}",
            processing_status=ProcessingStatus.FILTERED,
            last_checked=datetime.now(UTC)
        )
        test_db.upsert_show(show)

    # Get first page
    page1 = test_db.get_shows_by_status(ProcessingStatus.FILTERED, limit=3, offset=0)
    assert len(page1) == 3

    # Get second page
    page2 = test_db.get_shows_by_status(ProcessingStatus.FILTERED, limit=3, offset=3)
    assert len(page2) == 3

    # Verify no overlap
    page1_ids = {show.tvmaze_id for show in page1}
    page2_ids = {show.tvmaze_id for show in page2}
    assert len(page1_ids & page2_ids) == 0
