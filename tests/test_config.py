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
