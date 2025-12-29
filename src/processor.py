"""Show filtering and processing logic."""

import hashlib
import json
import logging
from datetime import date
from typing import Optional

from .config import FiltersConfig, Selection, SonarrConfig
from .database import Database
from .models import Decision, ProcessingResult, ProcessingStatus, Show, SonarrParams
from .state import SyncState

logger = logging.getLogger(__name__)


class ShowProcessor:
    """
    Evaluates shows against configured selections.

    Processing flow:
    1. Check TVDB ID exists → RETRY if missing
    2. Check global excludes → FILTER if matches any
    3. Check selections → ADD if matches any selection
    4. No selection matched → FILTER
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
        Evaluate show against global excludes and selections.

        Returns ProcessingResult with decision and details.
        """
        # 1. Check TVDB ID first
        if show.tvdb_id is None:
            return ProcessingResult(
                decision=Decision.RETRY,
                reason="No TVDB ID available",
                filter_category="tvdb"
            )

        # 2. Check global excludes
        exclude_reason = self._matches_exclude(show)
        if exclude_reason:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason=exclude_reason,
                filter_category="exclude"
            )

        # 3. Check selections - at least one must be defined
        if not self.config.selections:
            return ProcessingResult(
                decision=Decision.FILTER,
                reason="No selections configured",
                filter_category="selection"
            )

        # 4. Check if show matches any selection (OR logic)
        for selection in self.config.selections:
            if self._matches_selection(show, selection):
                sonarr_params = self._build_sonarr_params(show)
                return ProcessingResult(
                    decision=Decision.ADD,
                    reason=f"Matched: {selection.name or 'unnamed selection'}",
                    sonarr_params=sonarr_params
                )

        # 5. No selection matched
        return ProcessingResult(
            decision=Decision.FILTER,
            reason="No selection matched",
            filter_category="selection"
        )

    def _matches_exclude(self, show: Show) -> Optional[str]:
        """
        Check if show matches any global exclude criteria.

        Returns reason string if excluded, None if not excluded.
        """
        exc = self.config.exclude

        # Check genres
        if exc.genres and show.genres:
            overlap = set(exc.genres) & set(show.genres)
            if overlap:
                return f"Excluded genre: {', '.join(sorted(overlap))}"

        # Check types
        if exc.types and show.type in exc.types:
            return f"Excluded type: {show.type}"

        # Check languages
        if exc.languages and show.language in exc.languages:
            return f"Excluded language: {show.language}"

        # Check countries
        if exc.countries and show.country in exc.countries:
            return f"Excluded country: {show.country}"

        # Check networks
        if exc.networks and show.network in exc.networks:
            return f"Excluded network: {show.network}"

        return None

    def _matches_selection(self, show: Show, sel: Selection) -> bool:
        """
        Check if show matches ALL criteria in a selection.

        Empty list/None for a criteria = no constraint (passes).
        """
        # Language filter
        if sel.languages and show.language not in sel.languages:
            return False

        # Country filter
        if sel.countries and show.country not in sel.countries:
            return False

        # Genre filter (show must have at least one matching genre)
        if sel.genres:
            show_genres = set(show.genres) if show.genres else set()
            if not (set(sel.genres) & show_genres):
                return False

        # Type filter
        if sel.types and show.type not in sel.types:
            return False

        # Network filter
        if sel.networks and show.network not in sel.networks:
            return False

        # Status filter
        if sel.status and show.status not in sel.status:
            return False

        # Premiered date range
        if sel.premiered:
            if sel.premiered.after:
                threshold = date.fromisoformat(sel.premiered.after)
                if not show.premiered or show.premiered < threshold:
                    return False
            if sel.premiered.before:
                threshold = date.fromisoformat(sel.premiered.before)
                if not show.premiered or show.premiered > threshold:
                    return False

        # Ended date range
        if sel.ended:
            if sel.ended.after:
                threshold = date.fromisoformat(sel.ended.after)
                if not show.ended or show.ended < threshold:
                    return False
            if sel.ended.before:
                threshold = date.fromisoformat(sel.ended.before)
                if not show.ended or show.ended > threshold:
                    return False

        # Rating range
        if sel.rating:
            show_rating = getattr(show, 'rating', None)
            if sel.rating.min is not None:
                if show_rating is None or show_rating < sel.rating.min:
                    return False
            if sel.rating.max is not None:
                if show_rating is None or show_rating > sel.rating.max:
                    return False

        # Runtime range
        if sel.runtime:
            if sel.runtime.min is not None:
                if show.runtime is None or show.runtime < sel.runtime.min:
                    return False
            if sel.runtime.max is not None:
                if show.runtime is None or show.runtime > sel.runtime.max:
                    return False

        return True

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
    # Build hashable representation of config
    exclude_dict = {
        "genres": sorted(config.exclude.genres),
        "types": sorted(config.exclude.types),
        "languages": sorted(config.exclude.languages),
        "countries": sorted(config.exclude.countries),
        "networks": sorted(config.exclude.networks),
    }

    selections_list = []
    for sel in config.selections:
        sel_dict = {
            "name": sel.name,
            "languages": sorted(sel.languages),
            "countries": sorted(sel.countries),
            "genres": sorted(sel.genres),
            "types": sorted(sel.types),
            "networks": sorted(sel.networks),
            "status": sorted(sel.status),
            "premiered": {
                "after": sel.premiered.after if sel.premiered else None,
                "before": sel.premiered.before if sel.premiered else None,
            },
            "ended": {
                "after": sel.ended.after if sel.ended else None,
                "before": sel.ended.before if sel.ended else None,
            },
            "rating": {
                "min": sel.rating.min if sel.rating else None,
                "max": sel.rating.max if sel.rating else None,
            },
            "runtime": {
                "min": sel.runtime.min if sel.runtime else None,
                "max": sel.runtime.max if sel.runtime else None,
            },
        }
        selections_list.append(sel_dict)

    filter_dict = {
        "exclude": exclude_dict,
        "selections": selections_list,
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
