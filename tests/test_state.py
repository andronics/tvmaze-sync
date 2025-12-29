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


# Additional tests for comprehensive coverage


@pytest.mark.unit
def test_state_save_atomic_write(temp_dir):
    """Test atomic write mechanics of save()."""
    from pathlib import Path

    state_path = temp_dir / "state.json"
    tmp_path = temp_dir / "state.json.tmp"

    state = SyncState(highest_tvmaze_id=555)
    state.save(state_path)

    # Main file should exist
    assert state_path.exists()
    # Temp file should be cleaned up
    assert not tmp_path.exists()

    # Verify content
    with open(state_path, 'r') as f:
        data = json.load(f)
    assert data["highest_tvmaze_id"] == 555


@pytest.mark.unit
def test_state_save_ioerror_cleanup(temp_dir, monkeypatch):
    """Test save() cleans up temp file on IOError."""
    from pathlib import Path
    import builtins

    state_path = temp_dir / "state.json"
    tmp_path = temp_dir / "state.json.tmp"

    # Mock open to raise IOError on temp file
    original_open = builtins.open
    call_count = [0]

    def mock_open(*args, **kwargs):
        call_count[0] += 1
        # Fail on second call (writing to temp file)
        if call_count[0] == 1 and str(args[0]).endswith('.tmp'):
            # Create the file first so cleanup can be tested
            f = original_open(*args, **kwargs)
            f.write('partial')
            f.close()
            raise IOError("Simulated write error")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(builtins, 'open', mock_open)

    state = SyncState(highest_tvmaze_id=777)

    # Should raise IOError
    with pytest.raises(IOError, match="Simulated write error"):
        state.save(state_path)

    # Temp file should be cleaned up
    assert not tmp_path.exists()


@pytest.mark.unit
def test_state_save_creates_directory(temp_dir):
    """Test save() creates parent directory if missing."""
    from pathlib import Path

    nested_dir = temp_dir / "nested" / "dir"
    state_path = nested_dir / "state.json"

    # Directory doesn't exist yet
    assert not nested_dir.exists()

    state = SyncState(highest_tvmaze_id=123)
    state.save(state_path)

    # Directory should be created
    assert nested_dir.exists()
    assert state_path.exists()


@pytest.mark.unit
def test_state_backup_nonexistent_file(temp_dir):
    """Test backup() with non-existent state file."""
    from pathlib import Path

    state_path = temp_dir / "state.json"
    backup_path = temp_dir / "state.json.bak"

    state = SyncState(highest_tvmaze_id=999)

    # Try to backup non-existent file
    state.backup(state_path)

    # Backup should not be created
    assert not backup_path.exists()


@pytest.mark.unit
def test_state_from_dict_invalid_datetimes():
    """Test from_dict() gracefully handles invalid datetime strings."""
    data = {
        "last_full_sync": "invalid-datetime",
        "last_incremental_sync": "also-invalid",
        "last_tvmaze_page": 100,
        "highest_tvmaze_id": 12345,
        "last_filter_hash": "abc123",
        "last_updates_check": "bad-format"
    }

    state = SyncState.from_dict(data)

    # Invalid datetimes should be ignored and set to None
    assert state.last_full_sync is None
    assert state.last_incremental_sync is None
    assert state.last_updates_check is None
    # Other fields should still work
    assert state.highest_tvmaze_id == 12345
    assert state.last_filter_hash == "abc123"


@pytest.mark.unit
def test_validate_state_invalid_datetime_strings():
    """Test validate_state() rejects invalid datetime strings."""
    data = {
        "last_full_sync": "not-a-valid-datetime",
        "last_incremental_sync": None,
        "last_tvmaze_page": 0,
        "highest_tvmaze_id": 0,
        "last_filter_hash": None,
        "last_updates_check": None
    }

    # Should fail validation due to invalid datetime
    assert validate_state(data) is False
