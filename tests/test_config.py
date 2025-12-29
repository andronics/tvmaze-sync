"""Tests for config module."""

import os
import pytest
import tempfile
from pathlib import Path

from src.config import (
    ConfigurationError,
    apply_env_overrides,
    load_config,
    resolve_env_value,
    validate_config,
)


@pytest.mark.unit
def test_resolve_env_value_direct():
    """Test resolving direct environment variable."""
    os.environ["TEST_VAR"] = "test_value"

    result = resolve_env_value("${TEST_VAR}")

    assert result == "test_value"

    del os.environ["TEST_VAR"]


@pytest.mark.unit
def test_resolve_env_value_file():
    """Test resolving environment variable from file."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("secret_value")
        temp_file = f.name

    os.environ["TEST_VAR_FILE"] = temp_file

    result = resolve_env_value("${TEST_VAR}")

    assert result == "secret_value"

    del os.environ["TEST_VAR_FILE"]
    os.unlink(temp_file)


@pytest.mark.unit
def test_resolve_env_value_missing():
    """Test resolving missing environment variable."""
    with pytest.raises(ConfigurationError):
        resolve_env_value("${NONEXISTENT_VAR}")


@pytest.mark.unit
def test_apply_env_overrides():
    """Test applying environment variable overrides."""
    os.environ["SONARR_URL"] = "http://test:8989"
    os.environ["FILTERS_GENRES_EXCLUDE"] = "Reality,Talk Show"
    os.environ["DRY_RUN"] = "true"

    config = {}
    config = apply_env_overrides(config)

    assert config.get("sonarr", {}).get("url") == "http://test:8989"
    assert config.get("filters", {}).get("genres", {}).get("exclude") == ["Reality", "Talk Show"]
    assert config.get("dry_run") is True

    del os.environ["SONARR_URL"]
    del os.environ["FILTERS_GENRES_EXCLUDE"]
    del os.environ["DRY_RUN"]


@pytest.mark.unit
def test_load_config_from_env_only():
    """Test loading config entirely from environment variables."""
    os.environ["SONARR_URL"] = "http://test:8989"
    os.environ["SONARR_API_KEY"] = "test_key"
    os.environ["SONARR_ROOT_FOLDER"] = "/tv"
    os.environ["SONARR_QUALITY_PROFILE"] = "HD"

    try:
        config = load_config(Path("/nonexistent/config.yaml"))

        assert config.sonarr.url == "http://test:8989"
        assert config.sonarr.api_key == "test_key"
        assert config.sonarr.root_folder == "/tv"
        assert config.sonarr.quality_profile == "HD"

    finally:
        del os.environ["SONARR_URL"]
        del os.environ["SONARR_API_KEY"]
        del os.environ["SONARR_ROOT_FOLDER"]
        del os.environ["SONARR_QUALITY_PROFILE"]


@pytest.mark.unit
def test_validate_config_invalid_logging_level(test_config):
    """Test config validation with invalid logging level."""
    from src.config import LoggingConfig

    # Create invalid config
    test_config = test_config.__class__(
        **{**test_config.__dict__, "logging": LoggingConfig(level="INVALID")}
    )

    with pytest.raises(ConfigurationError, match="Invalid logging.level"):
        validate_config(test_config)


@pytest.mark.unit
def test_validate_config_invalid_port(test_config):
    """Test config validation with invalid port."""
    from src.config import ServerConfig

    # Create invalid config
    test_config = test_config.__class__(
        **{**test_config.__dict__, "server": ServerConfig(port=99999)}
    )

    with pytest.raises(ConfigurationError, match="Invalid server.port"):
        validate_config(test_config)


@pytest.mark.unit
def test_validate_config_valid(test_config):
    """Test config validation with valid config."""
    # Should not raise
    validate_config(test_config)


# Additional tests for comprehensive coverage

@pytest.mark.unit
def test_resolve_env_in_dict_nested():
    """Test resolving environment variables in nested dictionaries."""
    from src.config import resolve_env_in_dict

    os.environ["TEST_URL"] = "http://localhost:8989"
    os.environ["TEST_KEY"] = "secret_key"

    data = {
        "level1": {
            "level2": {
                "url": "${TEST_URL}",
                "key": "${TEST_KEY}"
            }
        }
    }

    result = resolve_env_in_dict(data)

    assert result["level1"]["level2"]["url"] == "http://localhost:8989"
    assert result["level1"]["level2"]["key"] == "secret_key"

    del os.environ["TEST_URL"]
    del os.environ["TEST_KEY"]


@pytest.mark.unit
def test_load_config_from_yaml():
    """Test loading config from YAML file."""
    import yaml

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "test_key",
                "root_folder": "/tv",
                "quality_profile": "HD-1080p"
            }
        }
        yaml.dump(config_data, f)
        config_path = Path(f.name)

    try:
        config = load_config(config_path)
        assert config.sonarr.url == "http://localhost:8989"
        assert config.sonarr.api_key == "test_key"
    finally:
        os.unlink(config_path)


@pytest.mark.unit
def test_load_config_yaml_parse_error():
    """Test loading config with invalid YAML."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("invalid: yaml: content: [")
        config_path = Path(f.name)

    try:
        with pytest.raises(ConfigurationError, match="Failed to parse"):
            load_config(config_path)
    finally:
        os.unlink(config_path)


@pytest.mark.unit
def test_load_config_missing_required_fields():
    """Test loading config with missing required Sonarr fields."""
    import yaml

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        # Missing api_key
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "root_folder": "/tv",
                "quality_profile": "HD-1080p"
            }
        }
        yaml.dump(config_data, f)
        config_path = Path(f.name)

    try:
        with pytest.raises(ConfigurationError):
            load_config(config_path)
    finally:
        os.unlink(config_path)


@pytest.mark.unit
def test_validate_config_invalid_update_window(test_config):
    """Test validation with invalid update window."""
    from src.config import TVMazeConfig

    test_config = test_config.__class__(
        **{**test_config.__dict__, "tvmaze": TVMazeConfig(update_window="invalid")}
    )

    with pytest.raises(ConfigurationError, match="Invalid tvmaze.update_window"):
        validate_config(test_config)


@pytest.mark.unit
def test_validate_config_invalid_monitor_mode(test_config):
    """Test validation with invalid monitor mode."""
    from src.config import SonarrConfig

    test_config = test_config.__class__(
        **{**test_config.__dict__, "sonarr": SonarrConfig(
            url="http://localhost:8989",
            api_key="test",
            root_folder="/tv",
            quality_profile="HD",
            monitor="invalid_mode"
        )}
    )

    with pytest.raises(ConfigurationError, match="Invalid sonarr.monitor"):
        validate_config(test_config)


@pytest.mark.unit
def test_apply_env_overrides_integer_parsing():
    """Test integer parsing in environment overrides."""
    os.environ["FILTERS_MIN_RUNTIME"] = "30"
    os.environ["SERVER_PORT"] = "8080"

    config = {}
    config = apply_env_overrides(config)

    assert config.get("filters", {}).get("min_runtime") == 30
    assert config.get("server", {}).get("port") == 8080

    del os.environ["FILTERS_MIN_RUNTIME"]
    del os.environ["SERVER_PORT"]


@pytest.mark.unit
def test_resolve_env_value_file_not_found():
    """Test resolving env var when file doesn't exist."""
    os.environ["TEST_VAR_FILE"] = "/nonexistent/file.txt"

    with pytest.raises(ConfigurationError, match="File not found"):
        resolve_env_value("${TEST_VAR}")

    del os.environ["TEST_VAR_FILE"]


@pytest.mark.unit
def test_apply_env_overrides_boolean_parsing():
    """Test boolean parsing in environment overrides."""
    os.environ["DRY_RUN"] = "false"
    os.environ["SONARR_SEARCH_ON_ADD"] = "true"

    config = {}
    config = apply_env_overrides(config)

    assert config.get("dry_run") is False
    assert config.get("sonarr", {}).get("search_on_add") is True

    del os.environ["DRY_RUN"]
    del os.environ["SONARR_SEARCH_ON_ADD"]


@pytest.mark.unit
def test_validate_config_invalid_premiered_after(test_config):
    """Test validation with invalid premiered_after date format."""
    from src.config import FiltersConfig

    test_config = test_config.__class__(
        **{**test_config.__dict__, "filters": FiltersConfig(premiered_after="invalid-date")}
    )

    with pytest.raises(ConfigurationError, match="Invalid filters.premiered_after"):
        validate_config(test_config)
