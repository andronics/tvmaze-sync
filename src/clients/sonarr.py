"""Sonarr API client wrapping pyarr with validation."""

import logging
from dataclasses import dataclass
from typing import Optional

from pyarr import SonarrAPI
from pyarr.exceptions import PyarrError

from ..config import ConfigurationError, SonarrConfig
from ..models import SonarrParams

logger = logging.getLogger(__name__)


@dataclass
class AddResult:
    """Result of adding a series to Sonarr."""

    success: bool
    series_id: Optional[int] = None
    exists: bool = False
    error: Optional[str] = None


class SonarrClient:
    """
    Sonarr API client with startup validation.

    Wraps pyarr SonarrAPI with:
    - Configuration validation
    - Name-to-ID resolution
    - Error handling
    - Metric tracking
    """

    def __init__(self, config: SonarrConfig):
        self.config = config
        self._api = SonarrAPI(config.url, config.api_key)

        # Populated by validate_config()
        self._root_folder_path: Optional[str] = None
        self._root_folder_id: Optional[int] = None
        self._quality_profile_id: Optional[int] = None
        self._language_profile_id: Optional[int] = None
        self._tag_ids: list[int] = []
        self._sonarr_version: Optional[str] = None

    @property
    def version(self) -> Optional[str]:
        """Get Sonarr version."""
        return self._sonarr_version

    @version.setter
    def version(self, value: Optional[str]) -> None:
        """Set Sonarr version."""
        self._sonarr_version = value

    def validate_config(self) -> None:
        """
        Validate Sonarr configuration at startup.

        Checks:
        1. API connectivity
        2. Sonarr version detection
        3. Root folder exists
        4. Quality profile exists
        5. Language profile exists (v3 only)
        6. Tags exist

        Raises ConfigurationError with details on failure.
        """
        self._validate_connection()
        self._validate_root_folder()
        self._validate_quality_profile()
        self._validate_language_profile()
        self._validate_tags()

        logger.info("Sonarr configuration validated successfully")

    def _validate_connection(self) -> None:
        """Verify API connectivity and detect version."""
        try:
            status = self._api.get_system_status()
            self._sonarr_version = status.get('version', 'unknown')
            logger.info(f"Connected to Sonarr {self._sonarr_version}")
        except Exception as e:
            raise ConfigurationError(f"Cannot connect to Sonarr at {self.config.url}: {e}")

    def _validate_root_folder(self) -> int:
        """Validate configured root folder exists and return its ID."""
        try:
            folders = self._api.get_root_folder()
        except Exception as e:
            raise ConfigurationError(f"Failed to get root folders from Sonarr: {e}")

        if not folders:
            raise ConfigurationError("No root folders found in Sonarr")

        by_path = {f['path']: f['id'] for f in folders}
        by_id = {f['id']: f['path'] for f in folders}

        configured = self.config.root_folder

        # Check if configured as ID
        if isinstance(configured, int) or (isinstance(configured, str) and configured.isdigit()):
            folder_id = int(configured)
            if folder_id not in by_id:
                raise ConfigurationError(
                    f"Root folder ID {folder_id} not found. "
                    f"Available: {list(by_id.values())}"
                )
            self._root_folder_path = by_id[folder_id]
            self._root_folder_id = folder_id
        else:
            # Configured as path
            if configured not in by_path:
                raise ConfigurationError(
                    f"Root folder '{configured}' not found. "
                    f"Available: {list(by_path.keys())}"
                )
            self._root_folder_path = configured
            self._root_folder_id = by_path[configured]

        logger.info(f"Using root folder: {self._root_folder_path} (ID: {self._root_folder_id})")
        return self._root_folder_id

    def _validate_quality_profile(self) -> int:
        """Validate configured quality profile exists."""
        try:
            profiles = self._api.get_quality_profile()
        except Exception as e:
            raise ConfigurationError(f"Failed to get quality profiles from Sonarr: {e}")

        by_name = {p['name'].lower(): p['id'] for p in profiles}
        by_id = {p['id']: p['name'] for p in profiles}

        configured = self.config.quality_profile

        # Check if configured as ID
        if isinstance(configured, int) or (isinstance(configured, str) and configured.isdigit()):
            profile_id = int(configured)
            if profile_id not in by_id:
                raise ConfigurationError(
                    f"Quality profile ID {profile_id} not found. "
                    f"Available: {[f'{p['name']} ({p['id']})' for p in profiles]}"
                )
            self._quality_profile_id = profile_id
        else:
            if configured.lower() not in by_name:
                raise ConfigurationError(
                    f"Quality profile '{configured}' not found. "
                    f"Available: {[p['name'] for p in profiles]}"
                )
            self._quality_profile_id = by_name[configured.lower()]

        logger.info(f"Using quality profile ID: {self._quality_profile_id}")
        return self._quality_profile_id

    def _validate_language_profile(self) -> Optional[int]:
        """Validate language profile (Sonarr v3 only)."""
        # Check if Sonarr v4+ (no language profiles)
        if self._sonarr_version and self._sonarr_version.startswith('4'):
            self._language_profile_id = None
            logger.info("Sonarr v4 detected, language profiles not required")
            return None

        # For v3, language profile is required
        if not self.config.language_profile:
            raise ConfigurationError(
                "language_profile required for Sonarr v3"
            )

        try:
            profiles = self._api.get_language_profile()
        except Exception as e:
            # If the endpoint doesn't exist, assume v4+
            logger.info("Language profile endpoint not available, assuming Sonarr v4+")
            self._language_profile_id = None
            return None

        by_name = {p['name'].lower(): p['id'] for p in profiles}
        by_id = {p['id']: p['name'] for p in profiles}

        configured = self.config.language_profile

        # Check if configured as ID
        if isinstance(configured, int) or (isinstance(configured, str) and configured.isdigit()):
            profile_id = int(configured)
            if profile_id not in by_id:
                raise ConfigurationError(
                    f"Language profile ID {profile_id} not found. "
                    f"Available: {[f'{p['name']} ({p['id']})' for p in profiles]}"
                )
            self._language_profile_id = profile_id
        else:
            if configured.lower() not in by_name:
                raise ConfigurationError(
                    f"Language profile '{configured}' not found. "
                    f"Available: {[p['name'] for p in profiles]}"
                )
            self._language_profile_id = by_name[configured.lower()]

        logger.info(f"Using language profile ID: {self._language_profile_id}")
        return self._language_profile_id

    def _validate_tags(self) -> list[int]:
        """Validate configured tags exist."""
        if not self.config.tags:
            self._tag_ids = []
            return []

        try:
            tags = self._api.get_tag()
        except Exception as e:
            raise ConfigurationError(f"Failed to get tags from Sonarr: {e}")

        by_name = {t['label'].lower(): t['id'] for t in tags}
        by_id = {t['id']: t['label'] for t in tags}

        self._tag_ids = []
        for configured in self.config.tags:
            # Check if configured as ID
            if isinstance(configured, int) or (isinstance(configured, str) and configured.isdigit()):
                tag_id = int(configured)
                if tag_id not in by_id:
                    raise ConfigurationError(
                        f"Tag ID {tag_id} not found. "
                        f"Available: {[f'{t['label']} ({t['id']})' for t in tags]}"
                    )
                self._tag_ids.append(tag_id)
            else:
                if configured.lower() not in by_name:
                    raise ConfigurationError(
                        f"Tag '{configured}' not found. "
                        f"Available: {[t['label'] for t in tags]}"
                    )
                self._tag_ids.append(by_name[configured.lower()])

        logger.info(f"Using tag IDs: {self._tag_ids}")
        return self._tag_ids

    @property
    def validated_params(self) -> Optional[dict]:
        """Get validated Sonarr parameters.

        Returns None if validate_config() has not been called yet.
        """
        # If validation hasn't been run, return None
        if self._root_folder_path is None:
            return None

        return {
            'root_folder': self._root_folder_path,
            'root_folder_id': self._root_folder_id,
            'quality_profile_id': self._quality_profile_id,
            'language_profile_id': self._language_profile_id,
            'tag_ids': self._tag_ids,
        }

    def lookup_series(self, tvdb_id: int) -> Optional[dict]:
        """
        Lookup series by TVDB ID.

        Returns series dict if found, None otherwise.
        """
        try:
            results = self._api.lookup_series(term=f"tvdb:{tvdb_id}")
            if results and len(results) > 0:
                logger.debug(f"Found series for TVDB ID {tvdb_id}")
                return results[0]
            logger.debug(f"No series found for TVDB ID {tvdb_id}")
            return None
        except PyarrError as e:
            logger.warning(f"Sonarr lookup failed for TVDB {tvdb_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during Sonarr lookup for TVDB {tvdb_id}: {e}")
            return None

    def add_series(self, params: SonarrParams, series_data: dict) -> AddResult:
        """
        Add series to Sonarr.

        Returns AddResult indicating success/exists/failed.
        """
        try:
            # Call pyarr add_series with correct parameter order:
            # add_series(series, quality_profile_id, language_profile_id, root_dir, ...)
            result = self._api.add_series(
                series_data,
                params.quality_profile_id,
                params.language_profile_id if params.language_profile_id else 1,  # pyarr requires int, use 1 for v4
                params.root_folder,
                season_folder=True,
                monitored=True,
                search_for_missing_episodes=params.search_on_add
            )

            series_id = result.get('id')
            logger.info(f"Successfully added series: {params.title} (Sonarr ID: {series_id})")

            return AddResult(success=True, series_id=series_id)

        except PyarrError as e:
            error_str = str(e).lower()

            # Check if series already exists
            if 'already been added' in error_str or 'already exists' in error_str:
                logger.info(f"Series already exists in Sonarr: {params.title}")
                return AddResult(success=False, exists=True)

            # Other error
            logger.warning(f"Failed to add series {params.title}: {e}")
            return AddResult(success=False, error=str(e))

        except Exception as e:
            logger.error(f"Unexpected error adding series {params.title}: {e}")
            return AddResult(success=False, error=str(e))

    def is_healthy(self) -> bool:
        """Check if Sonarr is reachable."""
        try:
            self._api.get_system_status()
            return True
        except Exception:
            return False
