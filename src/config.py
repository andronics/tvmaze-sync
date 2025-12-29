"""Configuration loading, environment variable resolution, and validation."""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Configuration is invalid or missing required fields."""

    pass


@dataclass(frozen=True)
class TVMazeConfig:
    """TVMaze API configuration."""

    api_key: Optional[str] = None
    rate_limit: int = 20
    update_window: str = "week"  # day, week, month


@dataclass(frozen=True)
class SyncConfig:
    """Sync cycle configuration."""

    poll_interval: str = "6h"
    retry_delay: str = "1w"
    max_retries: int = 4


@dataclass(frozen=True)
class GenreFilter:
    """Genre filter configuration."""

    exclude: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TypeFilter:
    """Show type filter configuration."""

    include: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CountryFilter:
    """Country filter configuration."""

    include: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LanguageFilter:
    """Language filter configuration."""

    include: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StatusFilter:
    """Show status filter configuration."""

    exclude_ended: bool = True


@dataclass(frozen=True)
class PremieredFilter:
    """Premiere date filter configuration."""

    after: Optional[str] = None  # ISO date string


@dataclass(frozen=True)
class FiltersConfig:
    """All filter configurations."""

    genres: GenreFilter = field(default_factory=GenreFilter)
    types: TypeFilter = field(default_factory=TypeFilter)
    countries: CountryFilter = field(default_factory=CountryFilter)
    languages: LanguageFilter = field(default_factory=LanguageFilter)
    status: StatusFilter = field(default_factory=StatusFilter)
    premiered: PremieredFilter = field(default_factory=PremieredFilter)
    min_runtime: Optional[int] = None


@dataclass(frozen=True)
class SonarrConfig:
    """Sonarr API configuration."""

    url: str
    api_key: str
    root_folder: str
    quality_profile: str | int
    language_profile: Optional[str | int] = None
    monitor: str = "all"
    search_on_add: bool = True
    tags: list[str | int] = field(default_factory=list)


@dataclass(frozen=True)
class StorageConfig:
    """Storage path configuration."""

    path: str = "/data"


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"  # json, text


@dataclass(frozen=True)
class ServerConfig:
    """HTTP server configuration."""

    enabled: bool = True
    port: int = 8080


@dataclass(frozen=True)
class Config:
    """Complete application configuration."""

    tvmaze: TVMazeConfig
    sync: SyncConfig
    filters: FiltersConfig
    sonarr: SonarrConfig
    storage: StorageConfig
    logging: LoggingConfig
    server: ServerConfig
    dry_run: bool = False


def resolve_env_value(value: str) -> str:
    """
    Resolve environment variable placeholders.

    Supports:
    - ${VAR} - Direct environment variable
    - ${VAR_FILE} - Read value from file (Docker secrets pattern)

    For ${VAR_FILE}:
    1. Look for VAR_FILE env var containing path
    2. Read and strip file contents
    3. Fall back to VAR if VAR_FILE not set

    Raises:
        ConfigurationError: If variable not found
    """
    if not isinstance(value, str):
        return value

    # Pattern to match ${VAR} or ${VAR_FILE}
    pattern = r'\$\{([^}]+)\}'

    def replacer(match):
        var_name = match.group(1)

        # Check for _FILE variant first (Docker secrets)
        file_var = f"{var_name}_FILE"
        if file_var in os.environ:
            file_path = os.environ[file_var]
            try:
                with open(file_path, 'r') as f:
                    return f.read().strip()
            except FileNotFoundError:
                raise ConfigurationError(
                    f"File specified in {file_var} not found: {file_path}"
                )
            except IOError as e:
                raise ConfigurationError(
                    f"Error reading file from {file_var}: {e}"
                )

        # Fall back to direct env var
        if var_name in os.environ:
            return os.environ[var_name]

        raise ConfigurationError(
            f"Environment variable ${{{var_name}}} not found"
        )

    return re.sub(pattern, replacer, value)


def resolve_env_in_dict(data: dict) -> dict:
    """Recursively resolve environment variables in dictionary."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = resolve_env_value(value)
        elif isinstance(value, dict):
            result[key] = resolve_env_in_dict(value)
        elif isinstance(value, list):
            result[key] = [
                resolve_env_value(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def apply_env_overrides(config_dict: dict) -> dict:
    """
    Apply environment variable overrides to config dict.

    Mapping: SECTION_KEY_SUBKEY → config[section][key][subkey]

    Examples:
        SONARR_URL → config['sonarr']['url']
        FILTERS_GENRES_EXCLUDE → config['filters']['genres']['exclude']
        SYNC_POLL_INTERVAL → config['sync']['poll_interval']

    List values use comma separation:
        FILTERS_GENRES_EXCLUDE=Reality,Talk Show,Game Show
    """
    # Map of environment variable to config path
    env_mappings = {
        # TVMaze
        "TVMAZE_API_KEY": ["tvmaze", "api_key"],
        "TVMAZE_RATE_LIMIT": ["tvmaze", "rate_limit"],
        "TVMAZE_UPDATE_WINDOW": ["tvmaze", "update_window"],
        # Sync
        "SYNC_POLL_INTERVAL": ["sync", "poll_interval"],
        "SYNC_RETRY_DELAY": ["sync", "retry_delay"],
        "SYNC_MAX_RETRIES": ["sync", "max_retries"],
        # Filters
        "FILTERS_GENRES_EXCLUDE": ["filters", "genres", "exclude"],
        "FILTERS_TYPES_INCLUDE": ["filters", "types", "include"],
        "FILTERS_COUNTRIES_INCLUDE": ["filters", "countries", "include"],
        "FILTERS_LANGUAGES_INCLUDE": ["filters", "languages", "include"],
        "FILTERS_STATUS_EXCLUDE_ENDED": ["filters", "status", "exclude_ended"],
        "FILTERS_PREMIERED_AFTER": ["filters", "premiered", "after"],
        "FILTERS_MIN_RUNTIME": ["filters", "min_runtime"],
        # Sonarr
        "SONARR_URL": ["sonarr", "url"],
        "SONARR_API_KEY": ["sonarr", "api_key"],
        "SONARR_ROOT_FOLDER": ["sonarr", "root_folder"],
        "SONARR_QUALITY_PROFILE": ["sonarr", "quality_profile"],
        "SONARR_LANGUAGE_PROFILE": ["sonarr", "language_profile"],
        "SONARR_MONITOR": ["sonarr", "monitor"],
        "SONARR_SEARCH_ON_ADD": ["sonarr", "search_on_add"],
        "SONARR_TAGS": ["sonarr", "tags"],
        # Storage
        "STORAGE_PATH": ["storage", "path"],
        # Logging
        "LOGGING_LEVEL": ["logging", "level"],
        "LOGGING_FORMAT": ["logging", "format"],
        # Server
        "SERVER_ENABLED": ["server", "enabled"],
        "SERVER_PORT": ["server", "port"],
        # Dry run
        "DRY_RUN": ["dry_run"],
    }

    for env_var, path in env_mappings.items():
        if env_var in os.environ:
            value = os.environ[env_var]

            # Type conversion based on the target field
            if env_var.endswith("_EXCLUDE") or env_var.endswith("_INCLUDE") or env_var == "SONARR_TAGS":
                # Comma-separated list
                value = [item.strip() for item in value.split(",") if item.strip()]
            elif env_var in ["SYNC_MAX_RETRIES", "TVMAZE_RATE_LIMIT", "SERVER_PORT", "FILTERS_MIN_RUNTIME"]:
                # Integer
                try:
                    value = int(value)
                except ValueError:
                    raise ConfigurationError(f"{env_var} must be an integer")
            elif env_var in ["FILTERS_STATUS_EXCLUDE_ENDED", "SONARR_SEARCH_ON_ADD", "SERVER_ENABLED", "DRY_RUN"]:
                # Boolean
                value = value.lower() in ("true", "1", "yes", "on")

            # Navigate to the target location in config dict
            current = config_dict
            for i, key in enumerate(path[:-1]):
                if key not in current:
                    current[key] = {}
                current = current[key]

            # Set the value
            current[path[-1]] = value

    return config_dict


def load_config(path: Path | None = None) -> Config:
    """
    Load configuration from YAML file with environment variable resolution.

    Resolution order:
    1. Load YAML file (default: /config/config.yaml)
    2. Resolve ${VAR} and ${VAR_FILE} placeholders
    3. Apply environment variable overrides
    4. Validate required fields and types
    5. Return frozen Config object

    Raises:
        ConfigurationError: If config is invalid or missing required fields
    """
    if path is None:
        path = Path(os.environ.get("CONFIG_PATH", "/config/config.yaml"))

    # Load YAML file
    try:
        with open(path, 'r') as f:
            config_dict = yaml.safe_load(f) or {}
    except FileNotFoundError:
        # If no config file, start with empty dict (all from env vars)
        logger.warning(f"Config file not found at {path}, using environment variables")
        config_dict = {}
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in config file: {e}")

    # Resolve environment variable placeholders in YAML
    config_dict = resolve_env_in_dict(config_dict)

    # Apply environment variable overrides
    config_dict = apply_env_overrides(config_dict)

    # Build config objects
    try:
        # TVMaze
        tvmaze_data = config_dict.get("tvmaze", {})
        tvmaze = TVMazeConfig(
            api_key=tvmaze_data.get("api_key"),
            rate_limit=tvmaze_data.get("rate_limit", 20),
            update_window=tvmaze_data.get("update_window", "week"),
        )

        # Sync
        sync_data = config_dict.get("sync", {})
        sync = SyncConfig(
            poll_interval=sync_data.get("poll_interval", "6h"),
            retry_delay=sync_data.get("retry_delay", "1w"),
            max_retries=sync_data.get("max_retries", 4),
        )

        # Filters
        filters_data = config_dict.get("filters", {})
        filters = FiltersConfig(
            genres=GenreFilter(
                exclude=filters_data.get("genres", {}).get("exclude", [])
            ),
            types=TypeFilter(
                include=filters_data.get("types", {}).get("include", [])
            ),
            countries=CountryFilter(
                include=filters_data.get("countries", {}).get("include", [])
            ),
            languages=LanguageFilter(
                include=filters_data.get("languages", {}).get("include", [])
            ),
            status=StatusFilter(
                exclude_ended=filters_data.get("status", {}).get("exclude_ended", True)
            ),
            premiered=PremieredFilter(
                after=filters_data.get("premiered", {}).get("after")
            ),
            min_runtime=filters_data.get("min_runtime"),
        )

        # Sonarr
        sonarr_data = config_dict.get("sonarr", {})
        if not sonarr_data.get("url"):
            raise ConfigurationError("sonarr.url is required")
        if not sonarr_data.get("api_key"):
            raise ConfigurationError("sonarr.api_key is required")
        if not sonarr_data.get("root_folder"):
            raise ConfigurationError("sonarr.root_folder is required")
        if not sonarr_data.get("quality_profile"):
            raise ConfigurationError("sonarr.quality_profile is required")

        sonarr = SonarrConfig(
            url=sonarr_data["url"],
            api_key=sonarr_data["api_key"],
            root_folder=sonarr_data["root_folder"],
            quality_profile=sonarr_data["quality_profile"],
            language_profile=sonarr_data.get("language_profile"),
            monitor=sonarr_data.get("monitor", "all"),
            search_on_add=sonarr_data.get("search_on_add", True),
            tags=sonarr_data.get("tags", []),
        )

        # Storage
        storage_data = config_dict.get("storage", {})
        storage = StorageConfig(
            path=storage_data.get("path", "/data")
        )

        # Logging
        logging_data = config_dict.get("logging", {})
        logging_config = LoggingConfig(
            level=logging_data.get("level", "INFO"),
            format=logging_data.get("format", "json"),
        )

        # Server
        server_data = config_dict.get("server", {})
        server = ServerConfig(
            enabled=server_data.get("enabled", True),
            port=server_data.get("port", 8080),
        )

        # Dry run
        dry_run = config_dict.get("dry_run", False)

        config = Config(
            tvmaze=tvmaze,
            sync=sync,
            filters=filters,
            sonarr=sonarr,
            storage=storage,
            logging=logging_config,
            server=server,
            dry_run=dry_run,
        )

        # Validate config
        validate_config(config)

        return config

    except KeyError as e:
        raise ConfigurationError(f"Missing required configuration: {e}")
    except TypeError as e:
        raise ConfigurationError(f"Invalid configuration type: {e}")


def validate_config(config: Config) -> None:
    """
    Validate configuration completeness and correctness.

    Checks:
    - Required fields present (sonarr.url, sonarr.api_key, sonarr.root_folder)
    - Valid types (port is int, poll_interval parses to duration)
    - Valid enum values (logging.level, logging.format)
    - No conflicting settings

    Raises:
        ConfigurationError: With details of all validation failures
    """
    errors = []

    # Validate logging level
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.logging.level.upper() not in valid_levels:
        errors.append(
            f"Invalid logging.level: {config.logging.level}. "
            f"Must be one of: {', '.join(valid_levels)}"
        )

    # Validate logging format
    valid_formats = ["json", "text"]
    if config.logging.format not in valid_formats:
        errors.append(
            f"Invalid logging.format: {config.logging.format}. "
            f"Must be one of: {', '.join(valid_formats)}"
        )

    # Validate server port
    if not isinstance(config.server.port, int) or config.server.port < 1 or config.server.port > 65535:
        errors.append(f"Invalid server.port: {config.server.port}. Must be between 1 and 65535")

    # Validate TVMaze update window
    valid_windows = ["day", "week", "month"]
    if config.tvmaze.update_window not in valid_windows:
        errors.append(
            f"Invalid tvmaze.update_window: {config.tvmaze.update_window}. "
            f"Must be one of: {', '.join(valid_windows)}"
        )

    # Validate Sonarr monitor mode
    valid_monitors = ["all", "future", "missing", "existing", "pilot", "firstSeason", "latestSeason", "none"]
    if config.sonarr.monitor not in valid_monitors:
        errors.append(
            f"Invalid sonarr.monitor: {config.sonarr.monitor}. "
            f"Must be one of: {', '.join(valid_monitors)}"
        )

    # Validate premiered.after date format if specified
    if config.filters.premiered.after:
        try:
            from datetime import date
            date.fromisoformat(config.filters.premiered.after)
        except ValueError:
            errors.append(
                f"Invalid filters.premiered.after: {config.filters.premiered.after}. "
                f"Must be ISO date format (YYYY-MM-DD)"
            )

    if errors:
        raise ConfigurationError("Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
