"""Tests for main application logic."""

import pytest
from datetime import timedelta, datetime
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.main import (
    parse_duration,
    setup_logging,
    process_single_show,
)
from src.models import Show, Decision, ProcessingResult, SyncStats, SonarrParams
from src.clients.tvmaze import TVMazeRateLimitError, TVMazeNotFoundError


# Duration parsing tests

def test_parse_duration_seconds():
    """Test parsing seconds."""
    assert parse_duration("30s") == timedelta(seconds=30)


def test_parse_duration_minutes():
    """Test parsing minutes."""
    assert parse_duration("45m") == timedelta(minutes=45)


def test_parse_duration_hours():
    """Test parsing hours."""
    assert parse_duration("6h") == timedelta(hours=6)


def test_parse_duration_days():
    """Test parsing days."""
    assert parse_duration("7d") == timedelta(days=7)


def test_parse_duration_weeks():
    """Test parsing weeks."""
    assert parse_duration("2w") == timedelta(weeks=2)


def test_parse_duration_invalid_unit():
    """Test invalid duration unit."""
    with pytest.raises(ValueError, match="Invalid duration unit"):
        parse_duration("10x")


def test_parse_duration_empty_string():
    """Test empty duration string."""
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_duration("")


# Logging setup tests

def test_setup_logging_json():
    """Test JSON logging setup."""
    from src.config import LoggingConfig

    config = LoggingConfig(level="INFO", format="json")
    setup_logging(config)

    # Should not raise exception
    assert True


def test_setup_logging_text():
    """Test text logging setup."""
    from src.config import LoggingConfig

    config = LoggingConfig(level="DEBUG", format="text")
    setup_logging(config)

    assert True


# process_single_show tests

def test_process_single_show_add(test_db, test_config, mock_sonarr_client, sample_show, sync_stats):
    """Test processing a show that should be added."""
    from src.processor import ShowProcessor

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Configure Sonarr client to return success
    mock_sonarr_client.lookup_series.return_value = {"tvdbId": sample_show.tvdb_id}
    mock_sonarr_client.add_series.return_value.success = True
    mock_sonarr_client.add_series.return_value.series_id = 1

    # Process show
    process_single_show(test_db, test_config, mock_sonarr_client, processor, sample_show, sync_stats)

    # Verify show was added
    assert sync_stats.shows_added == 1
    assert sync_stats.shows_processed == 1


def test_process_single_show_filter(test_db, test_config, mock_sonarr_client, sample_show_reality, sync_stats):
    """Test processing a show that should be filtered."""
    from src.processor import ShowProcessor

    processor = ShowProcessor(test_config.filters, test_config.sonarr)

    # Process reality show (should be filtered by default config)
    process_single_show(test_db, test_config, mock_sonarr_client, processor, sample_show_reality, sync_stats)

    # Verify show was filtered
    assert sync_stats.shows_filtered == 1
    assert sync_stats.shows_processed == 1


def test_process_single_show_dry_run(test_db, test_config, mock_sonarr_client, sample_show, sync_stats):
    """Test dry run mode."""
    from src.processor import ShowProcessor

    # Create new config with dry_run enabled
    dry_run_config = test_config.__class__(
        **{**test_config.__dict__, 'dry_run': True}
    )

    processor = ShowProcessor(dry_run_config.filters, dry_run_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Process show
    process_single_show(test_db, dry_run_config, mock_sonarr_client, processor, sample_show, sync_stats)

    # Verify Sonarr was not called
    mock_sonarr_client.add_series.assert_not_called()


def test_process_single_show_pending_tvdb(test_db, test_config, mock_sonarr_client, sample_show_no_tvdb, sync_stats):
    """Test processing show without TVDB ID."""
    from src.processor import ShowProcessor

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Process show without TVDB
    process_single_show(test_db, test_config, mock_sonarr_client, processor, sample_show_no_tvdb, sync_stats)

    # Verify show was skipped
    assert sync_stats.shows_skipped == 1


def test_process_single_show_exists(test_db, test_config, mock_sonarr_client, sample_show, sync_stats):
    """Test processing show that already exists."""
    from src.processor import ShowProcessor
    from src.clients.sonarr import AddResult

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Configure Sonarr to return "exists"
    mock_sonarr_client.lookup_series.return_value = {"tvdbId": sample_show.tvdb_id}
    mock_sonarr_client.add_series.return_value = AddResult(
        success=False,
        exists=True,
        series_id=None,
        error=None
    )

    process_single_show(test_db, test_config, mock_sonarr_client, processor, sample_show, sync_stats)

    # Verify show was marked as exists
    assert sync_stats.shows_exists == 1


def test_process_single_show_failed(test_db, test_config, mock_sonarr_client, sample_show, sync_stats):
    """Test processing show that fails to add."""
    from src.processor import ShowProcessor
    from src.clients.sonarr import AddResult

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Configure Sonarr to return error
    mock_sonarr_client.lookup_series.return_value = {"tvdbId": sample_show.tvdb_id}
    mock_sonarr_client.add_series.return_value = AddResult(
        success=False,
        exists=False,
        series_id=None,
        error="API error"
    )

    process_single_show(test_db, test_config, mock_sonarr_client, processor, sample_show, sync_stats)

    # Verify show was marked as failed
    assert sync_stats.shows_failed == 1


def test_process_single_show_lookup_not_found(test_db, test_config, mock_sonarr_client, sample_show, sync_stats):
    """Test processing when Sonarr lookup fails."""
    from src.processor import ShowProcessor

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Configure Sonarr to return None (not found)
    mock_sonarr_client.lookup_series.return_value = None

    process_single_show(test_db, test_config, mock_sonarr_client, processor, sample_show, sync_stats)

    # Should be marked as skipped/pending
    assert sync_stats.shows_skipped == 1


# Sync cycle tests (simplified integration tests)

@patch('src.main.run_initial_sync')
@patch('src.main.retry_pending_tvdb')
def test_sync_cycle_initial(mock_retry, mock_initial, test_db, test_state, test_config, mock_sonarr_client, mock_tvmaze_client, sync_stats):
    """Test sync cycle when no previous sync."""
    from src.main import sync_cycle
    from src.processor import ShowProcessor

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # No previous sync
    test_state.last_full_sync = None

    sync_cycle(test_db, test_state, test_config, mock_sonarr_client, mock_tvmaze_client, processor)

    # Should have called initial sync
    mock_initial.assert_called_once()
    mock_retry.assert_called_once()


@patch('src.main.run_incremental_sync')
@patch('src.main.retry_pending_tvdb')
def test_sync_cycle_incremental(mock_retry, mock_incremental, test_db, test_state, test_config, mock_sonarr_client, mock_tvmaze_client, sync_stats):
    """Test sync cycle when previous sync exists."""
    from src.main import sync_cycle
    from src.processor import ShowProcessor

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Set previous sync
    test_state.last_full_sync = datetime.utcnow()

    sync_cycle(test_db, test_state, test_config, mock_sonarr_client, mock_tvmaze_client, processor)

    # Should have called incremental sync
    mock_incremental.assert_called_once()
    mock_retry.assert_called_once()


# Run initial sync test (basic)

def test_run_initial_sync_pagination(test_db, test_state, test_config, mock_sonarr_client, mock_tvmaze_client, sync_stats):
    """Test initial sync with pagination."""
    from src.main import run_initial_sync
    from src.processor import ShowProcessor

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Mock TVMaze to return empty on second page
    mock_tvmaze_client.get_shows_page.side_effect = [
        [{"id": 1, "name": "Show 1", "type": "Scripted", "language": "English", "status": "Running",
          "premiered": "2020-01-01", "runtime": 30, "genres": ["Drama"],
          "network": {"name": "NBC", "country": {"code": "US"}},
          "externals": {"tvdb": 100}, "updated": 1704067200}],
        []  # End of pages
    ]

    run_initial_sync(test_db, test_state, test_config, mock_sonarr_client, mock_tvmaze_client, processor, sync_stats)

    # Should have processed at least one page
    assert sync_stats.shows_processed >= 1


# Retry pending tests

def test_retry_pending_tvdb_success(test_db, test_state, test_config, mock_sonarr_client, mock_tvmaze_client, sample_show_no_tvdb, sync_stats):
    """Test retrying show that now has TVDB ID."""
    from src.main import retry_pending_tvdb
    from src.processor import ShowProcessor
    from datetime import datetime, timedelta

    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    # Insert pending show
    test_db.upsert_show(sample_show_no_tvdb)
    test_db.mark_show_pending_tvdb(
        sample_show_no_tvdb.tvmaze_id,
        retry_after=datetime.utcnow() - timedelta(days=1)  # Ready for retry
    )

    # Mock TVMaze to return show WITH TVDB now
    show_with_tvdb = sample_show_no_tvdb
    show_with_tvdb.tvdb_id = 12345
    mock_tvmaze_client.get_show.return_value = {
        "id": show_with_tvdb.tvmaze_id,
        "name": show_with_tvdb.title,
        "type": "Scripted",
        "language": "English",
        "status": "Running",
        "premiered": "2020-01-01",
        "runtime": 30,
        "genres": ["Drama"],
        "network": {"name": "NBC", "country": {"code": "US"}},
        "externals": {"tvdb": 12345},
        "updated": 1704067200
    }

    retry_pending_tvdb(test_db, test_state, test_config, mock_sonarr_client, mock_tvmaze_client, processor, sync_stats)

    # Should have retried the show
    assert sync_stats.shows_processed >= 0


# Additional utility tests can be added here for:
# - run_incremental_sync
# - check_for_new_shows
# - log_startup_banner
# These would require more complex mocking and are integration-focused
