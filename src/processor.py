"""Show filtering and processing logic."""

import hashlib
import json
import logging
from datetime import date
from typing import Optional

from .config import FiltersConfig, SonarrConfig
from .database import Database
from .models import Decision, ProcessingResult, ProcessingStatus, Show, SonarrParams
from .state import SyncState

logger = logging.getLogger(__name__)


class ShowProcessor:
    """
    Evaluates shows against configured filters.

    Designed with clean interface to allow future replacement
    with rule engine implementation.
    """

    def __init__(self, config: FiltersConfig, sonarr_config: SonarrConfig):
        self.config = config
        self.sonarr_config = sonarr_config
        self._validated_sonarr_params: Optional[dict] = None

    def set_validated_sonarr_params(
        self,
        root_folder: str,
        quality_profile_id: int,
        language_profile_id: Optional[int],
        tag_ids: list[int]
    ) -> None:
        """Set pre-validated Sonarr parameters."""
        self._validated_sonarr_params = {
            'root_folder': root_folder,
            'quality_profile_id': quality_profile_id,
            'language_profile_id': language_profile_id,
            'tag_ids': tag_ids,
        }

    def process(self, show: Show) -> ProcessingResult:
        """
        Evaluate show against filters and return decision.

        Filter evaluation order:
        1. Check TVDB ID exists → RETRY if missing
        2. Check genres → FILTER if excluded genre
        3. Check type → FILTER if not in included types
        4. Check language → FILTER if not in included languages
        5. Check country → FILTER if not in included countries
        6. Check status → FILTER if ended and exclude_ended=true
        7. Check premiered date → FILTER if before threshold
        8. Check runtime → FILTER if below minimum
        9. All passed → ADD

        Returns ProcessingResult with decision and details.
        """
        # Check TVDB ID first
        result = self._check_tvdb_id(show)
        if result:
            return result

        # Apply filters in order
        result = self._check_genres(show)
        if result:
            return result

        result = self._check_type(show)
        if result:
            return result

        result = self._check_language(show)
        if result:
            return result

        result = self._check_country(show)
        if result:
            return result

        result = self._check_status(show)
        if result:
            return result

        result = self._check_premiered(show)
        if result:
            return result

        result = self._check_runtime(show)
        if result:
            return result

        # All filters passed - build Sonarr params
        sonarr_params = self._build_sonarr_params(show)

        return ProcessingResult(
            decision=Decision.ADD,
            reason="Passed all filters",
            sonarr_params=sonarr_params
        )

    def _check_tvdb_id(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show has TVDB ID."""
        if show.tvdb_id is None:
            return ProcessingResult(
                decision=Decision.RETRY,
                reason="No TVDB ID available",
                filter_category="tvdb"
            )
        return None

    def _check_genres(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show has excluded genres."""
        if not self.config.genres.exclude:
            return None

        excluded = set(self.config.genres.exclude)
        show_genres = set(show.genres) if show.genres else set()
        overlap = excluded & show_genres

        if overlap:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Excluded genre: {', '.join(sorted(overlap))}",
                filter_category="genre"
            )
        return None

    def _check_type(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show type is in included list."""
        if not self.config.types.include:
            return None

        if show.type not in self.config.types.include:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Type not included: {show.type}",
                filter_category="type"
            )
        return None

    def _check_language(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show language is in included list."""
        if not self.config.languages.include:
            return None

        if show.language not in self.config.languages.include:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Language not included: {show.language}",
                filter_category="language"
            )
        return None

    def _check_country(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show country is in included list."""
        if not self.config.countries.include:
            return None

        if show.country not in self.config.countries.include:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Country not included: {show.country}",
                filter_category="country"
            )
        return None

    def _check_status(self, show: Show) -> Optional[ProcessingResult]:
        """Check if ended shows should be excluded."""
        if not self.config.status.exclude_ended:
            return None

        if show.status == "Ended":
            return ProcessingResult(
                decision=Decision.FILTER,
                reason="Show has ended",
                filter_category="status"
            )
        return None

    def _check_premiered(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show premiered after threshold."""
        if not self.config.premiered.after:
            return None

        threshold = date.fromisoformat(self.config.premiered.after)
        if show.premiered and show.premiered < threshold:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Premiered before {self.config.premiered.after}",
                filter_category="premiered"
            )
        return None

    def _check_runtime(self, show: Show) -> Optional[ProcessingResult]:
        """Check if show meets minimum runtime."""
        if not self.config.min_runtime:
            return None

        if show.runtime and show.runtime < self.config.min_runtime:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=f"Runtime {show.runtime}m below minimum {self.config.min_runtime}m",
                filter_category="runtime"
            )
        return None

    def _build_sonarr_params(self, show: Show) -> SonarrParams:
        """Build Sonarr parameters for show addition."""
        if not self._validated_sonarr_params:
            raise RuntimeError("Sonarr parameters not validated. Call set_validated_sonarr_params() first.")

        return SonarrParams(
            tvdb_id=show.tvdb_id,
            title=show.title,
            root_folder=self._validated_sonarr_params['root_folder'],
            quality_profile_id=self._validated_sonarr_params['quality_profile_id'],
            language_profile_id=self._validated_sonarr_params.get('language_profile_id'),
            monitor=self.sonarr_config.monitor,
            search_on_add=self.sonarr_config.search_on_add,
            tags=self._validated_sonarr_params.get('tag_ids', [])
        )


def compute_filter_hash(config: FiltersConfig) -> str:
    """
    Compute hash of filter configuration.

    Used to detect filter changes between runs.
    Returns 16-character hex string.
    """
    filter_dict = {
        "genres_exclude": sorted(config.genres.exclude) if config.genres.exclude else [],
        "types_include": sorted(config.types.include) if config.types.include else [],
        "countries_include": sorted(config.countries.include) if config.countries.include else [],
        "languages_include": sorted(config.languages.include) if config.languages.include else [],
        "exclude_ended": config.status.exclude_ended,
        "premiered_after": config.premiered.after,
        "min_runtime": config.min_runtime,
    }

    serialized = json.dumps(filter_dict, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def check_filter_change(
    state: SyncState,
    config: FiltersConfig,
    db: Database,
    processor: ShowProcessor
) -> int:
    """
    Check for filter changes and re-evaluate if needed.

    Returns count of shows re-evaluated.
    """
    current_hash = compute_filter_hash(config)

    if state.last_filter_hash and state.last_filter_hash != current_hash:
        logger.info("Filter configuration changed, re-evaluating filtered shows...")
        count = re_evaluate_filtered_shows(db, processor)
        state.last_filter_hash = current_hash
        return count

    state.last_filter_hash = current_hash
    return 0


def re_evaluate_filtered_shows(db: Database, processor: ShowProcessor) -> int:
    """
    Re-evaluate all filtered shows against current filters.

    Shows that now pass filters are marked for Sonarr addition.
    Returns count of shows that changed status.
    """
    changed = 0

    for show in db.get_all_filtered_shows():
        result = processor.process(show)

        if result.decision == Decision.ADD:
            # Was filtered, now passes
            db.update_show_status(show.tvmaze_id, ProcessingStatus.PENDING)
            changed += 1
            logger.info(f"Show now passes filters: {show.title}")
        elif result.decision == Decision.FILTER:
            # Still filtered, possibly different reason
            if result.reason != show.filter_reason:
                db.mark_show_filtered(
                    show.tvmaze_id,
                    result.reason,
                    result.filter_category
                )
                logger.debug(f"Updated filter reason for {show.title}: {result.reason}")

    logger.info(f"Re-evaluated filtered shows: {changed} now pass filters")
    return changed
