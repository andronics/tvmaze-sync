"""Tests for state module."""

import json
import pytest
from datetime import datetime

from src.state import SyncState, validate_state


@pytest.mark.unit
def test_state_save_and_load(temp_dir):
    """Test saving and loading state."""
    state_path = temp_dir / "state.json"

    state = SyncState(
        last_full_sync=datetime(2024, 1, 1, 10, 0, 0),
        highest_tvmaze_id=12345,
        last_filter_hash="abc123"
    )

    state.save(state_path)

    loaded_state = SyncState.load(state_path)

    assert loaded_state.last_full_sync == state.last_full_sync
    assert loaded_state.highest_tvmaze_id == state.highest_tvmaze_id
    assert loaded_state.last_filter_hash == state.last_filter_hash


@pytest.mark.unit
def test_state_load_nonexistent_file(temp_dir):
    """Test loading state when file doesn't exist."""
    state_path = temp_dir / "state.json"

    state = SyncState.load(state_path)

    # Should return fresh state
    assert state.last_full_sync is None
    assert state.highest_tvmaze_id == 0


@pytest.mark.unit
def test_state_backup(temp_dir):
    """Test state backup creation."""
    state_path = temp_dir / "state.json"
    backup_path = temp_dir / "state.json.bak"

    state = SyncState(highest_tvmaze_id=12345)
    state.save(state_path)

    state.backup(state_path)

    assert backup_path.exists()


@pytest.mark.unit
def test_state_to_dict():
    """Test state serialization to dict."""
    state = SyncState(
        last_full_sync=datetime(2024, 1, 1, 10, 0, 0),
        highest_tvmaze_id=12345
    )

    data = state.to_dict()

    assert data["last_full_sync"] == "2024-01-01T10:00:00"
    assert data["highest_tvmaze_id"] == 12345


@pytest.mark.unit
def test_state_from_dict():
    """Test state deserialization from dict."""
    data = {
        "last_full_sync": "2024-01-01T10:00:00",
        "last_incremental_sync": None,
        "last_tvmaze_page": 100,
        "highest_tvmaze_id": 12345,
        "last_filter_hash": "abc123",
        "last_updates_check": None
    }

    state = SyncState.from_dict(data)

    assert state.last_full_sync == datetime(2024, 1, 1, 10, 0, 0)
    assert state.highest_tvmaze_id == 12345
    assert state.last_filter_hash == "abc123"


@pytest.mark.unit
def test_validate_state_valid():
    """Test state validation with valid data."""
    data = {
        "last_full_sync": "2024-01-01T10:00:00",
        "last_incremental_sync": None,
        "last_tvmaze_page": 0,
        "highest_tvmaze_id": 0,
        "last_filter_hash": None,
        "last_updates_check": None
    }

    assert validate_state(data) is True


@pytest.mark.unit
def test_validate_state_missing_key():
    """Test state validation with missing required key."""
    data = {
        "last_full_sync": "2024-01-01T10:00:00",
        # Missing last_tvmaze_page
        "highest_tvmaze_id": 0
    }

    assert validate_state(data) is False


@pytest.mark.unit
def test_validate_state_invalid_type():
    """Test state validation with invalid type."""
    data = {
        "last_tvmaze_page": "not_an_int",  # Should be int
        "highest_tvmaze_id": 0
    }

    assert validate_state(data) is False


@pytest.mark.unit
def test_state_load_with_corrupt_file_and_backup(temp_dir):
    """Test loading state with corrupt file but valid backup."""
    state_path = temp_dir / "state.json"
    backup_path = temp_dir / "state.json.bak"

    # Create corrupt main file
    with open(state_path, 'w') as f:
        f.write("{ invalid json")

    # Create valid backup
    backup_state = SyncState(highest_tvmaze_id=999)
    backup_data = backup_state.to_dict()
    with open(backup_path, 'w') as f:
        json.dump(backup_data, f)

    # Should load from backup
    loaded_state = SyncState.load(state_path)
    assert loaded_state.highest_tvmaze_id == 999
