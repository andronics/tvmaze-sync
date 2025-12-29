"""Tests for Sonarr API client."""

from unittest.mock import Mock, patch, PropertyMock
import pytest

from pyarr.exceptions import PyarrResourceNotFound, PyarrConnectionError

from src.clients.sonarr import SonarrClient, AddResult
from src.config import SonarrConfig, ConfigurationError


# Initialization tests

def test_sonarr_client_initialization():
    """Test SonarrClient initialization."""
    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)

    assert client.config == config
    assert client._validated_params is None


# Connection validation tests

@patch('src.clients.sonarr.SonarrAPI')
def test_validate_connection_success(mock_sonarr_api, sonarr_system_status):
    """Test successful connection validation."""
    mock_api = Mock()
    mock_api.get_system_status.return_value = sonarr_system_status
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client._validate_connection()

    mock_api.get_system_status.assert_called_once()


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_connection_failure(mock_sonarr_api):
    """Test connection validation failure."""
    mock_api = Mock()
    mock_api.get_system_status.side_effect = PyarrConnectionError("Connection failed")
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://invalid:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)

    with pytest.raises(ConfigurationError, match="Cannot connect to Sonarr"):
        client._validate_connection()


# Root folder validation tests

@patch('src.clients.sonarr.SonarrAPI')
def test_validate_root_folder_by_path(mock_sonarr_api, sonarr_root_folders):
    """Test root folder validation by path."""
    mock_api = Mock()
    mock_api.get_root_folder.return_value = sonarr_root_folders
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api
    folder_id = client._validate_root_folder()

    assert folder_id == 1


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_root_folder_by_id(mock_sonarr_api, sonarr_root_folders):
    """Test root folder validation by ID."""
    mock_api = Mock()
    mock_api.get_root_folder.return_value = sonarr_root_folders
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="2",  # ID as string
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api
    folder_id = client._validate_root_folder()

    assert folder_id == 2


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_root_folder_not_found(mock_sonarr_api, sonarr_root_folders):
    """Test root folder not found error."""
    mock_api = Mock()
    mock_api.get_root_folder.return_value = sonarr_root_folders
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/nonexistent",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    with pytest.raises(ConfigurationError, match="Root folder not found"):
        client._validate_root_folder()


# Quality profile validation tests

@patch('src.clients.sonarr.SonarrAPI')
def test_validate_quality_profile_by_name(mock_sonarr_api, sonarr_quality_profiles):
    """Test quality profile validation by name."""
    mock_api = Mock()
    mock_api.get_quality_profile.return_value = sonarr_quality_profiles
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api
    profile_id = client._validate_quality_profile()

    assert profile_id == 1


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_quality_profile_case_insensitive(mock_sonarr_api, sonarr_quality_profiles):
    """Test quality profile validation is case-insensitive."""
    mock_api = Mock()
    mock_api.get_quality_profile.return_value = sonarr_quality_profiles
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="hd-1080p"  # lowercase
    )

    client = SonarrClient(config)
    client.api = mock_api
    profile_id = client._validate_quality_profile()

    assert profile_id == 1


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_quality_profile_by_id(mock_sonarr_api, sonarr_quality_profiles):
    """Test quality profile validation by ID."""
    mock_api = Mock()
    mock_api.get_quality_profile.return_value = sonarr_quality_profiles
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="2"
    )

    client = SonarrClient(config)
    client.api = mock_api
    profile_id = client._validate_quality_profile()

    assert profile_id == 2


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_quality_profile_not_found(mock_sonarr_api, sonarr_quality_profiles):
    """Test quality profile not found error."""
    mock_api = Mock()
    mock_api.get_quality_profile.return_value = sonarr_quality_profiles
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="NonExistent"
    )

    client = SonarrClient(config)
    client.api = mock_api

    with pytest.raises(ConfigurationError, match="Quality profile not found"):
        client._validate_quality_profile()


# Language profile validation tests (v3 vs v4)

@patch('src.clients.sonarr.SonarrAPI')
def test_validate_language_profile_v3_required(mock_sonarr_api, sonarr_system_status, sonarr_language_profiles):
    """Test language profile required for v3."""
    # Mock v3
    v3_status = sonarr_system_status.copy()
    v3_status["version"] = "3.0.10.0"

    mock_api = Mock()
    mock_api.get_system_status.return_value = v3_status
    mock_api.get_language_profile.return_value = sonarr_language_profiles
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p",
        language_profile="English"
    )

    client = SonarrClient(config)
    client.api = mock_api
    client.version = "3.0.10.0"
    profile_id = client._validate_language_profile()

    assert profile_id == 1


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_language_profile_v4_optional(mock_sonarr_api, sonarr_system_status):
    """Test language profile optional for v4."""
    mock_api = Mock()
    mock_api.get_system_status.return_value = sonarr_system_status
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
        # No language_profile
    )

    client = SonarrClient(config)
    client.api = mock_api
    client.version = "4.0.0.0"
    profile_id = client._validate_language_profile()

    # Should return None for v4
    assert profile_id is None


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_language_profile_endpoint_missing(mock_sonarr_api):
    """Test handling when language profile endpoint doesn't exist (v4)."""
    mock_api = Mock()
    mock_api.get_language_profile.side_effect = PyarrResourceNotFound("Not found")
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p",
        language_profile="English"
    )

    client = SonarrClient(config)
    client.api = mock_api
    client.version = "4.0.0.0"

    # Should return None when endpoint doesn't exist (v4)
    profile_id = client._validate_language_profile()
    assert profile_id is None


# Tag validation tests

@patch('src.clients.sonarr.SonarrAPI')
def test_validate_tags_by_name(mock_sonarr_api, sonarr_tags):
    """Test tag validation by name."""
    mock_api = Mock()
    mock_api.get_tag.return_value = sonarr_tags
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p",
        tags=["tvmaze", "auto"]
    )

    client = SonarrClient(config)
    client.api = mock_api
    tag_ids = client._validate_tags()

    assert tag_ids == [1, 2]


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_tags_by_id(mock_sonarr_api, sonarr_tags):
    """Test tag validation by ID."""
    mock_api = Mock()
    mock_api.get_tag.return_value = sonarr_tags
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p",
        tags=["1", "2"]
    )

    client = SonarrClient(config)
    client.api = mock_api
    tag_ids = client._validate_tags()

    assert tag_ids == [1, 2]


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_tags_empty(mock_sonarr_api):
    """Test tag validation with empty tags."""
    mock_api = Mock()
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p",
        tags=[]
    )

    client = SonarrClient(config)
    client.api = mock_api
    tag_ids = client._validate_tags()

    assert tag_ids == []
    mock_api.get_tag.assert_not_called()


@patch('src.clients.sonarr.SonarrAPI')
def test_validate_tags_not_found(mock_sonarr_api, sonarr_tags):
    """Test tag not found error."""
    mock_api = Mock()
    mock_api.get_tag.return_value = sonarr_tags
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p",
        tags=["nonexistent"]
    )

    client = SonarrClient(config)
    client.api = mock_api

    with pytest.raises(ConfigurationError, match="Tag not found"):
        client._validate_tags()


# Full validation test

@patch('src.clients.sonarr.SonarrAPI')
def test_validate_config_full_flow(
    mock_sonarr_api,
    sonarr_system_status,
    sonarr_root_folders,
    sonarr_quality_profiles,
    sonarr_tags
):
    """Test complete validation flow."""
    mock_api = Mock()
    mock_api.get_system_status.return_value = sonarr_system_status
    mock_api.get_root_folder.return_value = sonarr_root_folders
    mock_api.get_quality_profile.return_value = sonarr_quality_profiles
    mock_api.get_tag.return_value = sonarr_tags
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p",
        tags=["tvmaze"]
    )

    client = SonarrClient(config)
    client.validate_config()

    assert client._validated_params is not None
    assert client._validated_params["root_folder_id"] == 1
    assert client._validated_params["quality_profile_id"] == 1
    assert client._validated_params["tag_ids"] == [1]


# validated_params property test

@patch('src.clients.sonarr.SonarrAPI')
def test_validated_params_property(mock_sonarr_api):
    """Test validated_params property."""
    mock_api = Mock()
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client._validated_params = {
        "root_folder_id": 1,
        "quality_profile_id": 1,
        "language_profile_id": None,
        "tag_ids": []
    }

    params = client.validated_params
    assert params["root_folder_id"] == 1


# lookup_series tests

@patch('src.clients.sonarr.SonarrAPI')
def test_lookup_series_found(mock_sonarr_api, sonarr_series_lookup):
    """Test successful series lookup."""
    mock_api = Mock()
    mock_api.lookup_series.return_value = sonarr_series_lookup
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    result = client.lookup_series(tvdb_id=81189)

    assert result is not None
    assert result["tvdbId"] == 81189
    assert result["title"] == "Breaking Bad"
    mock_api.lookup_series.assert_called_once_with(term="tvdb:81189")


@patch('src.clients.sonarr.SonarrAPI')
def test_lookup_series_not_found(mock_sonarr_api):
    """Test series not found returns None."""
    mock_api = Mock()
    mock_api.lookup_series.return_value = []  # Empty list
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    result = client.lookup_series(tvdb_id=99999)

    assert result is None


@patch('src.clients.sonarr.SonarrAPI')
def test_lookup_series_pyarr_error(mock_sonarr_api):
    """Test PyarrError handling in lookup."""
    mock_api = Mock()
    mock_api.lookup_series.side_effect = PyarrConnectionError("API error")
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    result = client.lookup_series(tvdb_id=81189)

    assert result is None


# add_series tests

@patch('src.clients.sonarr.SonarrAPI')
def test_add_series_success(mock_sonarr_api):
    """Test successful series addition."""
    mock_api = Mock()
    mock_api.add_series.return_value = {"id": 1}
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    from src.models import SonarrParams

    params = SonarrParams(
        root_folder_id=1,
        quality_profile_id=1,
        language_profile_id=None,
        monitor="all",
        search_on_add=True,
        tag_ids=[]
    )

    series_data = {"tvdbId": 81189, "title": "Breaking Bad"}

    result = client.add_series(params, series_data)

    assert result.success is True
    assert result.series_id == 1
    assert result.exists is False
    assert result.error is None


@patch('src.clients.sonarr.SonarrAPI')
def test_add_series_already_exists(mock_sonarr_api):
    """Test series already exists handling."""
    mock_api = Mock()
    error = PyarrResourceNotFound("already exists")
    error.response = Mock()
    error.response.text = "This series has already been added"
    mock_api.add_series.side_effect = error
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    from src.models import SonarrParams

    params = SonarrParams(
        root_folder_id=1,
        quality_profile_id=1,
        language_profile_id=None,
        monitor="all",
        search_on_add=True,
        tag_ids=[]
    )

    result = client.add_series(params, {})

    assert result.success is False
    assert result.exists is True
    assert result.series_id is None


@patch('src.clients.sonarr.SonarrAPI')
def test_add_series_pyarr_error(mock_sonarr_api):
    """Test PyarrError handling in add_series."""
    mock_api = Mock()
    error = PyarrConnectionError("API error")
    error.response = None
    mock_api.add_series.side_effect = error
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    from src.models import SonarrParams

    params = SonarrParams(
        root_folder_id=1,
        quality_profile_id=1,
        language_profile_id=None,
        monitor="all",
        search_on_add=True,
        tag_ids=[]
    )

    result = client.add_series(params, {})

    assert result.success is False
    assert result.exists is False
    assert "API error" in result.error


# is_healthy test

@patch('src.clients.sonarr.SonarrAPI')
def test_is_healthy_true(mock_sonarr_api, sonarr_system_status):
    """Test healthy status check."""
    mock_api = Mock()
    mock_api.get_system_status.return_value = sonarr_system_status
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    assert client.is_healthy() is True


@patch('src.clients.sonarr.SonarrAPI')
def test_is_healthy_false(mock_sonarr_api):
    """Test unhealthy status check."""
    mock_api = Mock()
    mock_api.get_system_status.side_effect = Exception("Connection error")
    mock_sonarr_api.return_value = mock_api

    config = SonarrConfig(
        url="http://localhost:8989",
        api_key="test_key",
        root_folder="/tv",
        quality_profile="HD-1080p"
    )

    client = SonarrClient(config)
    client.api = mock_api

    assert client.is_healthy() is False
