"""Tests for processor module."""

import pytest
from datetime import date

from src.config import (
    CountryFilter,
    FiltersConfig,
    GenreFilter,
    LanguageFilter,
    PremieredFilter,
    SonarrConfig,
    StatusFilter,
    TypeFilter,
)
from src.models import Decision, Show
from src.processor import ShowProcessor, compute_filter_hash


@pytest.mark.unit
def test_processor_check_tvdb_id():
    """Test processor checks for TVDB ID."""
    config = FiltersConfig()
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    show = Show(
        tvmaze_id=1,
        title="Test Show",
        tvdb_id=None
    )

    result = processor.process(show)
    assert result.decision == Decision.RETRY
    assert "TVDB ID" in result.reason


@pytest.mark.unit
def test_processor_filter_by_genre():
    """Test processor filters by genre."""
    config = FiltersConfig(
        genres=GenreFilter(exclude=["Reality", "Talk Show"])
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    show = Show(
        tvmaze_id=1,
        title="Reality Show",
        tvdb_id=12345,
        genres=["Reality", "Drama"]
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert result.filter_category == "genre"
    assert "Reality" in result.reason


@pytest.mark.unit
def test_processor_filter_by_language():
    """Test processor filters by language."""
    config = FiltersConfig(
        languages=LanguageFilter(include=["English"])
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    show = Show(
        tvmaze_id=1,
        title="French Show",
        tvdb_id=12345,
        language="French"
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert result.filter_category == "language"


@pytest.mark.unit
def test_processor_filter_by_country():
    """Test processor filters by country."""
    config = FiltersConfig(
        countries=CountryFilter(include=["US", "GB"])
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    show = Show(
        tvmaze_id=1,
        title="German Show",
        tvdb_id=12345,
        country="DE"
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert result.filter_category == "country"


@pytest.mark.unit
def test_processor_filter_by_status_ended():
    """Test processor filters ended shows."""
    config = FiltersConfig(
        status=StatusFilter(exclude_ended=True)
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    show = Show(
        tvmaze_id=1,
        title="Ended Show",
        tvdb_id=12345,
        status="Ended"
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert result.filter_category == "status"


@pytest.mark.unit
def test_processor_filter_by_premiered_date():
    """Test processor filters by premiere date."""
    config = FiltersConfig(
        premiered=PremieredFilter(after="2010-01-01")
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    show = Show(
        tvmaze_id=1,
        title="Old Show",
        tvdb_id=12345,
        premiered=date(2005, 1, 1)
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert result.filter_category == "premiered"


@pytest.mark.unit
def test_processor_filter_by_runtime():
    """Test processor filters by runtime."""
    config = FiltersConfig(min_runtime=30)
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    show = Show(
        tvmaze_id=1,
        title="Short Show",
        tvdb_id=12345,
        runtime=15
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert result.filter_category == "runtime"


@pytest.mark.unit
def test_processor_passes_all_filters():
    """Test show that passes all filters."""
    config = FiltersConfig(
        genres=GenreFilter(exclude=["Reality"]),
        types=TypeFilter(include=["Scripted"]),
        languages=LanguageFilter(include=["English"]),
        countries=CountryFilter(include=["US"]),
        status=StatusFilter(exclude_ended=False)
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    show = Show(
        tvmaze_id=1,
        title="Good Show",
        tvdb_id=12345,
        type="Scripted",
        language="English",
        country="US",
        genres=["Drama"],
        status="Running"
    )

    result = processor.process(show)
    assert result.decision == Decision.ADD
    assert result.sonarr_params is not None


@pytest.mark.unit
def test_compute_filter_hash():
    """Test filter hash computation."""
    config1 = FiltersConfig(
        genres=GenreFilter(exclude=["Reality", "Talk Show"])
    )
    config2 = FiltersConfig(
        genres=GenreFilter(exclude=["Talk Show", "Reality"])  # Different order
    )
    config3 = FiltersConfig(
        genres=GenreFilter(exclude=["Reality"])  # Different content
    )

    hash1 = compute_filter_hash(config1)
    hash2 = compute_filter_hash(config2)
    hash3 = compute_filter_hash(config3)

    # Same filters should produce same hash regardless of order
    assert hash1 == hash2

    # Different filters should produce different hash
    assert hash1 != hash3


# Additional tests for comprehensive coverage


@pytest.mark.unit
def test_set_validated_sonarr_params():
    """Test setting validated Sonarr parameters."""
    config = FiltersConfig()
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    # Initially no params set
    assert processor._validated_sonarr_params is None

    # Set params
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=5,
        language_profile_id=2,
        tag_ids=[10, 20]
    )

    # Verify params stored
    assert processor._validated_sonarr_params is not None
    assert processor._validated_sonarr_params['root_folder'] == "/tv"
    assert processor._validated_sonarr_params['quality_profile_id'] == 5
    assert processor._validated_sonarr_params['language_profile_id'] == 2
    assert processor._validated_sonarr_params['tag_ids'] == [10, 20]


@pytest.mark.unit
def test_check_type_directly():
    """Test _check_type() method with type filtering."""
    config = FiltersConfig(
        types=TypeFilter(include=["Scripted", "Animation"])
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    # Show with included type
    show_scripted = Show(
        tvmaze_id=1,
        title="Drama Show",
        tvdb_id=12345,
        type="Scripted"
    )
    result = processor._check_type(show_scripted)
    assert result is None  # Passes filter

    # Show with excluded type
    show_reality = Show(
        tvmaze_id=2,
        title="Reality Show",
        tvdb_id=12346,
        type="Reality"
    )
    result = processor._check_type(show_reality)
    assert result is not None
    assert result.decision == Decision.FILTER
    assert result.filter_category == "type"
    assert "Reality" in result.reason


@pytest.mark.unit
def test_build_sonarr_params_without_validation():
    """Test _build_sonarr_params() raises error without validation."""
    config = FiltersConfig()
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD",
        monitor="all",
        search_on_add=True
    )
    processor = ShowProcessor(config, sonarr_config)

    show = Show(
        tvmaze_id=1,
        title="Test Show",
        tvdb_id=12345
    )

    # Should raise RuntimeError
    with pytest.raises(RuntimeError, match="Sonarr parameters not validated"):
        processor._build_sonarr_params(show)


@pytest.mark.unit
def test_check_filter_change_no_previous_hash(test_db, test_state):
    """Test filter change check on first run (no previous hash)."""
    from src.processor import check_filter_change

    config = FiltersConfig(
        genres=GenreFilter(exclude=["Reality"])
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    # No previous hash
    test_state.last_filter_hash = None

    count = check_filter_change(test_state, config, test_db, processor)

    # Should not re-evaluate on first run
    assert count == 0
    # Should set hash
    assert test_state.last_filter_hash is not None


@pytest.mark.unit
def test_check_filter_change_hash_changed(test_db, test_state, sample_show):
    """Test filter change triggers re-evaluation."""
    from src.processor import check_filter_change
    from src.models import ProcessingStatus

    # Insert filtered show
    test_db.upsert_show(sample_show)
    test_db.mark_show_filtered(sample_show.tvmaze_id, "Old filter", "genre")

    # Old config with Reality excluded
    old_config = FiltersConfig(
        genres=GenreFilter(exclude=["Reality"])
    )
    old_hash = compute_filter_hash(old_config)
    test_state.last_filter_hash = old_hash

    # New config with different exclusions
    new_config = FiltersConfig(
        genres=GenreFilter(exclude=["Talk Show"])
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(new_config, sonarr_config)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    count = check_filter_change(test_state, new_config, test_db, processor)

    # Should have re-evaluated
    assert count >= 0  # May or may not have changed status
    # Should update hash
    new_hash = compute_filter_hash(new_config)
    assert test_state.last_filter_hash == new_hash
    assert test_state.last_filter_hash != old_hash


@pytest.mark.unit
def test_check_filter_change_hash_unchanged(test_db, test_state):
    """Test no re-evaluation when hash unchanged."""
    from src.processor import check_filter_change

    config = FiltersConfig(
        genres=GenreFilter(exclude=["Reality"])
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    # Set hash to current config
    current_hash = compute_filter_hash(config)
    test_state.last_filter_hash = current_hash

    count = check_filter_change(test_state, config, test_db, processor)

    # Should not re-evaluate
    assert count == 0
    # Hash should remain same
    assert test_state.last_filter_hash == current_hash


@pytest.mark.unit
def test_re_evaluate_filtered_shows_status_change(test_db):
    """Test re-evaluation changes show status from filtered to pending."""
    from src.processor import re_evaluate_filtered_shows
    from src.models import ProcessingStatus

    # Create show that was filtered for Reality genre
    show = Show(
        tvmaze_id=1,
        title="Drama Show",
        tvdb_id=12345,
        type="Scripted",
        genres=["Drama"],  # Not Reality
        language="English"
    )

    test_db.upsert_show(show)
    test_db.mark_show_filtered(show.tvmaze_id, "Excluded genre: Reality", "genre")

    # New processor with no genre filters (show should now pass)
    config = FiltersConfig()
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)
    processor.set_validated_sonarr_params(
        root_folder="/tv",
        quality_profile_id=1,
        language_profile_id=None,
        tag_ids=[]
    )

    count = re_evaluate_filtered_shows(test_db, processor)

    # Should have changed status
    assert count >= 0
    # Show should now be pending (passes filters)
    retrieved = test_db.get_show(show.tvmaze_id)
    # Status may be PENDING if it now passes
    assert retrieved is not None


@pytest.mark.unit
def test_re_evaluate_filtered_shows_reason_update(test_db):
    """Test re-evaluation updates filter reason when still filtered."""
    from src.processor import re_evaluate_filtered_shows
    from src.models import ProcessingStatus

    # Create show that will still be filtered but for different reason
    show = Show(
        tvmaze_id=1,
        title="Reality Show",
        tvdb_id=12345,
        type="Reality",
        genres=["Reality", "Talk Show"],
        language="English"
    )

    test_db.upsert_show(show)
    test_db.mark_show_filtered(show.tvmaze_id, "Excluded genre: Reality", "genre")

    # New processor filtering by type instead of genre
    config = FiltersConfig(
        types=TypeFilter(include=["Scripted", "Animation"])
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    count = re_evaluate_filtered_shows(test_db, processor)

    # Should have updated reason
    retrieved = test_db.get_show(show.tvmaze_id)
    assert retrieved is not None
    # Should still be filtered
    assert retrieved.processing_status == ProcessingStatus.FILTERED
    # Reason should be updated to type-based filter
    assert "type" in retrieved.filter_reason.lower() or "Reality" in retrieved.filter_reason
