"""Pytest fixtures for testing."""

import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from src.config import (
    Config,
    FiltersConfig,
    GenreFilter,
    LoggingConfig,
    ServerConfig,
    SonarrConfig,
    StatusFilter,
    StorageConfig,
    SyncConfig,
    TVMazeConfig,
)
from src.database import Database
from src.models import Show
from src.state import SyncState


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_db(temp_dir):
    """Create test database."""
    db_path = temp_dir / "test.db"
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def test_state(temp_dir):
    """Create test state."""
    state_path = temp_dir / "state.json"
    state = SyncState()
    yield state


@pytest.fixture
def sample_show():
    """Create sample show for testing."""
    return Show(
        tvmaze_id=1,
        tvdb_id=12345,
        title="Breaking Bad",
        language="English",
        country="US",
        type="Scripted",
        status="Ended",
        premiered=date(2008, 1, 20),
        genres=["Drama", "Crime", "Thriller"],
        runtime=47,
        last_checked=datetime.utcnow()
    )


@pytest.fixture
def sample_show_no_tvdb():
    """Create sample show without TVDB ID for testing."""
    return Show(
        tvmaze_id=2,
        tvdb_id=None,
        title="Some Show",
        language="English",
        country="US",
        type="Scripted",
        status="Running",
        last_checked=datetime.utcnow()
    )


@pytest.fixture
def test_config():
    """Create test configuration."""
    return Config(
        tvmaze=TVMazeConfig(),
        sync=SyncConfig(),
        filters=FiltersConfig(
            genres=GenreFilter(exclude=["Reality", "Talk Show"]),
            status=StatusFilter(exclude_ended=True)
        ),
        sonarr=SonarrConfig(
            url="http://localhost:8989",
            api_key="test_api_key",
            root_folder="/tv",
            quality_profile="HD-1080p"
        ),
        storage=StorageConfig(path="/tmp/test"),
        logging=LoggingConfig(),
        server=ServerConfig(),
        dry_run=False
    )


@pytest.fixture
def tvmaze_show_response():
    """Sample TVMaze API show response."""
    return {
        "id": 1,
        "name": "Breaking Bad",
        "type": "Scripted",
        "language": "English",
        "status": "Ended",
        "premiered": "2008-01-20",
        "ended": "2013-09-29",
        "runtime": 47,
        "genres": ["Drama", "Crime", "Thriller"],
        "network": {
            "name": "AMC",
            "country": {"code": "US"}
        },
        "webChannel": None,
        "externals": {
            "tvdb": 81189,
            "thetvdb": 81189,
            "imdb": "tt0903747"
        },
        "updated": 1704067200
    }
