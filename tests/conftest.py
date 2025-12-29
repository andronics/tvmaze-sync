"""Pytest fixtures for testing."""

import tempfile
from datetime import UTC, date, datetime
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
        last_checked=datetime.now(UTC)
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
        last_checked=datetime.now(UTC)
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


# Additional Show fixtures for edge cases
@pytest.fixture
def sample_show_web_channel():
    """Sample show with webChannel instead of network."""
    return Show(
        tvmaze_id=3,
        tvdb_id=67890,
        title="Stranger Things",
        language="English",
        country="US",
        type="Scripted",
        status="Running",
        premiered=date(2016, 7, 15),
        genres=["Drama", "Fantasy", "Horror"],
        runtime=50,
        last_checked=datetime.now(UTC)
    )


@pytest.fixture
def sample_show_reality():
    """Sample reality show for filtering tests."""
    return Show(
        tvmaze_id=4,
        tvdb_id=11111,
        title="Reality Show Example",
        language="English",
        country="US",
        type="Reality",
        status="Running",
        premiered=date(2020, 1, 1),
        genres=["Reality"],
        runtime=30,
        last_checked=datetime.now(UTC)
    )


# TVMaze API response fixtures
@pytest.fixture
def tvmaze_show_response_no_tvdb():
    """TVMaze show response without TVDB ID."""
    return {
        "id": 2,
        "name": "Some Web Series",
        "type": "Scripted",
        "language": "English",
        "status": "Running",
        "premiered": "2020-01-01",
        "runtime": 25,
        "genres": ["Comedy"],
        "webChannel": {
            "name": "YouTube",
            "country": None
        },
        "network": None,
        "externals": {
            "tvdb": None,
            "imdb": "tt1234567"
        },
        "updated": 1704067300
    }


@pytest.fixture
def tvmaze_updates_response():
    """TVMaze updates API response."""
    return {
        "1": 1704067200,
        "2": 1704067300,
        "3": 1704067400
    }


@pytest.fixture
def tvmaze_page_response():
    """TVMaze paginated shows response."""
    return [
        {
            "id": 1,
            "name": "Show 1",
            "type": "Scripted",
            "language": "English",
            "status": "Running",
            "premiered": "2020-01-01",
            "runtime": 30,
            "genres": ["Drama"],
            "network": {"name": "NBC", "country": {"code": "US"}},
            "webChannel": None,
            "externals": {"tvdb": 100, "imdb": "tt001"},
            "updated": 1704067200
        },
        {
            "id": 2,
            "name": "Show 2",
            "type": "Scripted",
            "language": "English",
            "status": "Ended",
            "premiered": "2015-01-01",
            "runtime": 45,
            "genres": ["Comedy"],
            "network": {"name": "CBS", "country": {"code": "US"}},
            "webChannel": None,
            "externals": {"tvdb": 200, "imdb": "tt002"},
            "updated": 1704067300
        }
    ]


# Sonarr API fixtures
@pytest.fixture
def sonarr_system_status():
    """Sonarr system status response."""
    return {
        "version": "4.0.0.0",
        "buildTime": "2023-01-01T00:00:00Z",
        "isDebug": False,
        "isProduction": True,
        "isAdmin": True,
        "isUserInteractive": False,
        "startupPath": "/app",
        "appData": "/config",
        "osName": "ubuntu",
        "osVersion": "22.04"
    }


@pytest.fixture
def sonarr_root_folders():
    """Sonarr root folders response."""
    return [
        {
            "id": 1,
            "path": "/tv",
            "accessible": True,
            "freeSpace": 1000000000000,
            "unmappedFolders": []
        },
        {
            "id": 2,
            "path": "/media/shows",
            "accessible": True,
            "freeSpace": 2000000000000,
            "unmappedFolders": []
        }
    ]


@pytest.fixture
def sonarr_quality_profiles():
    """Sonarr quality profiles response."""
    return [
        {
            "id": 1,
            "name": "HD-1080p",
            "upgradeAllowed": True,
            "cutoff": 3,
            "items": []
        },
        {
            "id": 2,
            "name": "SD",
            "upgradeAllowed": False,
            "cutoff": 1,
            "items": []
        }
    ]


@pytest.fixture
def sonarr_language_profiles():
    """Sonarr language profiles response (v3 only)."""
    return [
        {
            "id": 1,
            "name": "English",
            "upgradeAllowed": False,
            "cutoff": {"id": 1, "name": "English"},
            "languages": [{"language": {"id": 1, "name": "English"}, "allowed": True}]
        }
    ]


@pytest.fixture
def sonarr_tags():
    """Sonarr tags response."""
    return [
        {"id": 1, "label": "tvmaze"},
        {"id": 2, "label": "auto"}
    ]


@pytest.fixture
def sonarr_series_lookup():
    """Sonarr series lookup response."""
    return [
        {
            "title": "Breaking Bad",
            "sortTitle": "breaking bad",
            "seasonCount": 5,
            "totalEpisodeCount": 62,
            "episodeCount": 62,
            "episodeFileCount": 0,
            "sizeOnDisk": 0,
            "status": "ended",
            "overview": "A high school chemistry teacher...",
            "network": "AMC",
            "airTime": "22:00",
            "images": [],
            "seasons": [],
            "year": 2008,
            "path": "",
            "profileId": 0,
            "seasonFolder": True,
            "monitored": False,
            "useSceneNumbering": False,
            "runtime": 47,
            "tvdbId": 81189,
            "tvRageId": 18164,
            "tvMazeId": 169,
            "firstAired": "2008-01-20T03:00:00Z",
            "lastInfoSync": None,
            "seriesType": "standard",
            "cleanTitle": "breakingbad",
            "imdbId": "tt0903747",
            "titleSlug": "breaking-bad",
            "certification": "TV-MA",
            "genres": ["Crime", "Drama", "Thriller"],
            "tags": [],
            "added": "0001-01-01T00:00:00Z",
            "ratings": {"votes": 0, "value": 0.0},
            "statistics": {
                "seasonCount": 5,
                "episodeFileCount": 0,
                "episodeCount": 62,
                "totalEpisodeCount": 62,
                "sizeOnDisk": 0,
                "percentOfEpisodes": 0.0
            }
        }
    ]


# Flask server fixtures
@pytest.fixture
def mock_flask_dependencies(test_db, test_state, test_config):
    """Create mock dependencies for Flask app."""
    from unittest.mock import Mock
    from src.scheduler import Scheduler
    from src.processor import ShowProcessor
    from datetime import timedelta

    # Create mock scheduler
    scheduler = Mock(spec=Scheduler)
    scheduler.is_running = False
    scheduler.next_run = datetime.now(UTC)
    scheduler.trigger_now = Mock()

    # Create mock Sonarr client
    sonarr_client = Mock()
    sonarr_client.is_healthy = Mock(return_value=True)

    # Create processor
    processor = ShowProcessor(test_config.filters, test_config.sonarr)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    return {
        'db': test_db,
        'state': test_state,
        'scheduler': scheduler,
        'sonarr_client': sonarr_client,
        'processor': processor,
        'config': test_config
    }


@pytest.fixture
def flask_app(mock_flask_dependencies):
    """Create Flask test app."""
    from src.server import create_app

    app = create_app(**mock_flask_dependencies)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def flask_client(flask_app):
    """Create Flask test client."""
    return flask_app.test_client()


# Scheduler fixtures
@pytest.fixture
def mock_sync_func():
    """Create mock sync function for scheduler."""
    from unittest.mock import Mock
    return Mock()


@pytest.fixture
def short_interval_scheduler(mock_sync_func):
    """Create scheduler with short interval for testing."""
    from datetime import timedelta
    from src.scheduler import Scheduler

    return Scheduler(
        interval=timedelta(seconds=0.1),
        sync_func=mock_sync_func
    )


# Mock SyncStats for main.py tests
@pytest.fixture
def sync_stats():
    """Create SyncStats for testing."""
    from src.models import SyncStats
    from datetime import datetime

    return SyncStats(started_at=datetime.now(UTC))


# Mock clients for integration tests
@pytest.fixture
def mock_tvmaze_client(tvmaze_show_response, tvmaze_page_response, tvmaze_updates_response):
    """Create mock TVMaze client."""
    from unittest.mock import Mock
    from src.clients.tvmaze import TVMazeClient

    client = Mock(spec=TVMazeClient)
    client.get_show = Mock(return_value=tvmaze_show_response)
    client.get_shows_page = Mock(return_value=tvmaze_page_response)
    client.get_updates = Mock(return_value={int(k): v for k, v in tvmaze_updates_response.items()})

    return client


@pytest.fixture
def mock_sonarr_client(sonarr_series_lookup):
    """Create mock Sonarr client."""
    from unittest.mock import Mock
    from src.clients.sonarr import SonarrClient, AddResult

    client = Mock(spec=SonarrClient)
    client.lookup_series = Mock(return_value=sonarr_series_lookup[0] if sonarr_series_lookup else None)
    client.add_series = Mock(return_value=AddResult(success=True, series_id=1))
    client.is_healthy = Mock(return_value=True)
    client.validated_params = {
        'root_folder_id': 1,
        'quality_profile_id': 1,
        'language_profile_id': None,
        'tag_ids': []
    }

    return client
