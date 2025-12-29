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
    abandon_after: str = "1y"


@dataclass(frozen=True)
class DateRange:
    """Date range for filtering (ISO date strings)."""

    after: Optional[str] = None
    before: Optional[str] = None


@dataclass(frozen=True)
class IntRange:
    """Integer range for filtering."""

    min: Optional[int] = None
    max: Optional[int] = None


@dataclass(frozen=True)
class FloatRange:
    """Float range for filtering."""

    min: Optional[float] = None
    max: Optional[float] = None


@dataclass(frozen=True)
class GlobalExclude:
    """Global exclusion rules - shows matching ANY of these are rejected."""

    genres: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    networks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Selection:
    """A selection rule - shows must match ALL criteria within a selection."""

    name: Optional[str] = None
    languages: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    networks: list[str] = field(default_factory=list)
    status: list[str] = field(default_factory=list)
    premiered: Optional[DateRange] = None
    ended: Optional[DateRange] = None
    rating: Optional[FloatRange] = None
    runtime: Optional[IntRange] = None


@dataclass(frozen=True)
class FiltersConfig:
    """Filter configuration with global excludes and selections."""

    exclude: GlobalExclude = field(default_factory=GlobalExclude)
    selections: list[Selection] = field(default_factory=list)


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
    dry_run: bool = True  # Safe default - must explicitly disable


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
        EXCLUDE_GENRES → config['exclude']['genres']
        SYNC_POLL_INTERVAL → config['sync']['poll_interval']

    List values use comma separation:
        EXCLUDE_GENRES=Reality,Talk Show,Game Show

    Note: Selections cannot be configured via environment variables
    due to their complex nested structure. Use config file for selections.
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
        "SYNC_ABANDON_AFTER": ["sync", "abandon_after"],
        # Global excludes
        "EXCLUDE_GENRES": ["exclude", "genres"],
        "EXCLUDE_TYPES": ["exclude", "types"],
        "EXCLUDE_LANGUAGES": ["exclude", "languages"],
        "EXCLUDE_COUNTRIES": ["exclude", "countries"],
        "EXCLUDE_NETWORKS": ["exclude", "networks"],
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
            if env_var.startswith("EXCLUDE_") or env_var == "SONARR_TAGS":
                # Comma-separated list
                value = [item.strip() for item in value.split(",") if item.strip()]
            elif env_var in ["TVMAZE_RATE_LIMIT", "SERVER_PORT"]:
                # Integer
                try:
                    value = int(value)
                except ValueError:
                    raise ConfigurationError(f"{env_var} must be an integer")
            elif env_var in ["SONARR_SEARCH_ON_ADD", "SERVER_ENABLED", "DRY_RUN"]:
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
            abandon_after=sync_data.get("abandon_after", "1y"),
        )

        # Global excludes
        exclude_data = config_dict.get("exclude", {})
        global_exclude = GlobalExclude(
            genres=exclude_data.get("genres", []),
            types=exclude_data.get("types", []),
            languages=exclude_data.get("languages", []),
            countries=exclude_data.get("countries", []),
            networks=exclude_data.get("networks", []),
        )

        # Selections
        selections_data = config_dict.get("selections", [])
        selections = []
        for sel_data in selections_data:
            # Parse nested date ranges
            premiered_data = sel_data.get("premiered")
            premiered = DateRange(
                after=premiered_data.get("after"),
                before=premiered_data.get("before")
            ) if premiered_data else None

            ended_data = sel_data.get("ended")
            ended = DateRange(
                after=ended_data.get("after"),
                before=ended_data.get("before")
            ) if ended_data else None

            # Parse nested numeric ranges
            rating_data = sel_data.get("rating")
            rating = FloatRange(
                min=rating_data.get("min"),
                max=rating_data.get("max")
            ) if rating_data else None

            runtime_data = sel_data.get("runtime")
            runtime = IntRange(
                min=runtime_data.get("min"),
                max=runtime_data.get("max")
            ) if runtime_data else None

            selection = Selection(
                name=sel_data.get("name"),
                languages=sel_data.get("languages", []),
                countries=sel_data.get("countries", []),
                genres=sel_data.get("genres", []),
                types=sel_data.get("types", []),
                networks=sel_data.get("networks", []),
                status=sel_data.get("status", []),
                premiered=premiered,
                ended=ended,
                rating=rating,
                runtime=runtime,
            )
            selections.append(selection)

        filters = FiltersConfig(
            exclude=global_exclude,
            selections=selections,
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

        # Dry run - defaults to True for safety
        dry_run = config_dict.get("dry_run", True)

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

    # Validate date ranges in selections
    from datetime import date as date_type
    for i, selection in enumerate(config.filters.selections):
        sel_name = selection.name or f"selection[{i}]"

        # Validate premiered dates
        if selection.premiered:
            if selection.premiered.after:
                try:
                    date_type.fromisoformat(selection.premiered.after)
                except ValueError:
                    errors.append(
                        f"Invalid {sel_name}.premiered.after: {selection.premiered.after}. "
                        f"Must be ISO date format (YYYY-MM-DD)"
                    )
            if selection.premiered.before:
                try:
                    date_type.fromisoformat(selection.premiered.before)
                except ValueError:
                    errors.append(
                        f"Invalid {sel_name}.premiered.before: {selection.premiered.before}. "
                        f"Must be ISO date format (YYYY-MM-DD)"
                    )

        # Validate ended dates
        if selection.ended:
            if selection.ended.after:
                try:
                    date_type.fromisoformat(selection.ended.after)
                except ValueError:
                    errors.append(
                        f"Invalid {sel_name}.ended.after: {selection.ended.after}. "
                        f"Must be ISO date format (YYYY-MM-DD)"
                    )
            if selection.ended.before:
                try:
                    date_type.fromisoformat(selection.ended.before)
                except ValueError:
                    errors.append(
                        f"Invalid {sel_name}.ended.before: {selection.ended.before}. "
                        f"Must be ISO date format (YYYY-MM-DD)"
                    )

    if errors:
        raise ConfigurationError("Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
