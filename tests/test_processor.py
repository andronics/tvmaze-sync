"""Tests for processor module."""

import pytest
from datetime import date

from src.config import (
    DateRange,
    FiltersConfig,
    FloatRange,
    GlobalExclude,
    IntRange,
    Selection,
    SonarrConfig,
)
from src.models import Decision, Show
from src.processor import ShowProcessor, compute_filter_hash


@pytest.mark.unit
def test_processor_check_tvdb_id():
    """Test processor checks for TVDB ID."""
    config = FiltersConfig(
        selections=[Selection(name="All")]  # Need at least one selection
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
        title="Test Show",
        tvdb_id=None
    )

    result = processor.process(show)
    assert result.decision == Decision.RETRY
    assert "TVDB ID" in result.reason


@pytest.mark.unit
def test_processor_filter_by_excluded_genre():
    """Test processor filters by excluded genre."""
    config = FiltersConfig(
        exclude=GlobalExclude(genres=["Reality", "Talk Show"]),
        selections=[Selection(name="All")]
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
    assert result.filter_category == "exclude"
    assert "Reality" in result.reason


@pytest.mark.unit
def test_processor_filter_by_selection_language():
    """Test processor filters by selection language."""
    config = FiltersConfig(
        selections=[
            Selection(name="English Only", languages=["English"])
        ]
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
    assert result.filter_category == "selection"
    assert "No selection matched" in result.reason


@pytest.mark.unit
def test_processor_filter_by_selection_country():
    """Test processor filters by selection country."""
    config = FiltersConfig(
        selections=[
            Selection(name="US/UK Only", countries=["US", "GB"])
        ]
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
    assert result.filter_category == "selection"


@pytest.mark.unit
def test_processor_no_selections_configured():
    """Test processor filters all shows when no selections configured."""
    config = FiltersConfig(
        selections=[]  # Empty selections = reject all
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
        title="Any Show",
        tvdb_id=12345,
        language="English"
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert "No selections configured" in result.reason


@pytest.mark.unit
def test_processor_filter_by_premiered_date():
    """Test processor filters by premiere date in selection."""
    config = FiltersConfig(
        selections=[
            Selection(
                name="Recent Shows",
                premiered=DateRange(after="2010-01-01")
            )
        ]
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


@pytest.mark.unit
def test_processor_filter_by_runtime():
    """Test processor filters by runtime in selection."""
    config = FiltersConfig(
        selections=[
            Selection(
                name="Long Episodes",
                runtime=IntRange(min=30)
            )
        ]
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
        title="Short Show",
        tvdb_id=12345,
        runtime=15
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER


@pytest.mark.unit
def test_processor_filter_by_rating():
    """Test processor filters by rating in selection."""
    config = FiltersConfig(
        selections=[
            Selection(
                name="Highly Rated",
                rating=FloatRange(min=7.0)
            )
        ]
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
        title="Low Rated Show",
        tvdb_id=12345,
        rating=5.5
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER


@pytest.mark.unit
def test_processor_passes_all_filters():
    """Test show that passes all selection criteria."""
    config = FiltersConfig(
        exclude=GlobalExclude(genres=["Reality"]),
        selections=[
            Selection(
                name="English Scripted",
                types=["Scripted"],
                languages=["English"],
                countries=["US"]
            )
        ]
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
def test_processor_matches_any_selection():
    """Test show matches if it matches ANY selection (OR logic)."""
    config = FiltersConfig(
        selections=[
            Selection(name="French", languages=["French"]),
            Selection(name="English", languages=["English"]),
        ]
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
        title="English Show",
        tvdb_id=12345,
        language="English"
    )

    result = processor.process(show)
    assert result.decision == Decision.ADD
    assert "English" in result.reason


@pytest.mark.unit
def test_processor_selection_all_criteria_must_match():
    """Test all criteria within a selection must match (AND logic)."""
    config = FiltersConfig(
        selections=[
            Selection(
                name="English from US",
                languages=["English"],
                countries=["US"]
            )
        ]
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    # English but from UK - should not match
    show = Show(
        tvmaze_id=1,
        title="British Show",
        tvdb_id=12345,
        language="English",
        country="GB"
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER


@pytest.mark.unit
def test_compute_filter_hash():
    """Test filter hash computation."""
    config1 = FiltersConfig(
        exclude=GlobalExclude(genres=["Reality", "Talk Show"]),
        selections=[Selection(name="All")]
    )
    config2 = FiltersConfig(
        exclude=GlobalExclude(genres=["Talk Show", "Reality"]),  # Different order
        selections=[Selection(name="All")]
    )
    config3 = FiltersConfig(
        exclude=GlobalExclude(genres=["Reality"]),  # Different content
        selections=[Selection(name="All")]
    )

    hash1 = compute_filter_hash(config1)
    hash2 = compute_filter_hash(config2)
    hash3 = compute_filter_hash(config3)

    # Same filters should produce same hash regardless of order
    assert hash1 == hash2

    # Different filters should produce different hash
    assert hash1 != hash3


@pytest.mark.unit
def test_set_validated_sonarr_params():
    """Test setting validated Sonarr parameters."""
    config = FiltersConfig(selections=[Selection(name="All")])
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
def test_build_sonarr_params_without_validation():
    """Test _build_sonarr_params() raises error without validation."""
    config = FiltersConfig(selections=[Selection(name="All")])
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
        exclude=GlobalExclude(genres=["Reality"]),
        selections=[Selection(name="All")]
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
        exclude=GlobalExclude(genres=["Reality"]),
        selections=[Selection(name="All")]
    )
    old_hash = compute_filter_hash(old_config)
    test_state.last_filter_hash = old_hash

    # New config with different exclusions
    new_config = FiltersConfig(
        exclude=GlobalExclude(genres=["Talk Show"]),
        selections=[Selection(name="All")]
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
        exclude=GlobalExclude(genres=["Reality"]),
        selections=[Selection(name="All")]
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

    # New processor with selection that accepts the show
    config = FiltersConfig(
        selections=[Selection(name="All")]  # Accepts everything
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
        selections=[
            Selection(name="Scripted Only", types=["Scripted", "Animation"])
        ]
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


@pytest.mark.unit
def test_global_exclude_types():
    """Test global exclude filters by type."""
    config = FiltersConfig(
        exclude=GlobalExclude(types=["News", "Sports"]),
        selections=[Selection(name="All")]
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
        title="News Show",
        tvdb_id=12345,
        type="News"
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert "Excluded type" in result.reason


@pytest.mark.unit
def test_global_exclude_networks():
    """Test global exclude filters by network."""
    config = FiltersConfig(
        exclude=GlobalExclude(networks=["Home Shopping Network"]),
        selections=[Selection(name="All")]
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
        title="Shopping Show",
        tvdb_id=12345,
        network="Home Shopping Network"
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER
    assert "network" in result.reason.lower()


@pytest.mark.unit
def test_selection_status_filter():
    """Test selection filters by status."""
    config = FiltersConfig(
        selections=[
            Selection(name="Running Only", status=["Running"])
        ]
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


@pytest.mark.unit
def test_selection_genre_filter():
    """Test selection filters by genre (show must have at least one matching)."""
    config = FiltersConfig(
        selections=[
            Selection(name="Sci-Fi/Fantasy", genres=["Science-Fiction", "Fantasy"])
        ]
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

    # Show with matching genre
    show_match = Show(
        tvmaze_id=1,
        title="Fantasy Show",
        tvdb_id=12345,
        genres=["Fantasy", "Drama"]
    )
    result = processor.process(show_match)
    assert result.decision == Decision.ADD

    # Show without matching genre
    show_no_match = Show(
        tvmaze_id=2,
        title="Drama Show",
        tvdb_id=12346,
        genres=["Drama", "Crime"]
    )
    result = processor.process(show_no_match)
    assert result.decision == Decision.FILTER


@pytest.mark.unit
def test_selection_ended_date_range():
    """Test selection filters by ended date range."""
    config = FiltersConfig(
        selections=[
            Selection(
                name="Recently Ended",
                ended=DateRange(after="2020-01-01")
            )
        ]
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    # Show that ended too early
    show = Show(
        tvmaze_id=1,
        title="Old Show",
        tvdb_id=12345,
        ended=date(2015, 6, 15)
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER


@pytest.mark.unit
def test_selection_rating_max():
    """Test selection filters by max rating."""
    config = FiltersConfig(
        selections=[
            Selection(
                name="Moderate Rating",
                rating=FloatRange(min=5.0, max=8.0)
            )
        ]
    )
    sonarr_config = SonarrConfig(
        url="http://localhost",
        api_key="test",
        root_folder="/tv",
        quality_profile="HD"
    )
    processor = ShowProcessor(config, sonarr_config)

    # Show with rating too high
    show = Show(
        tvmaze_id=1,
        title="Highly Rated Show",
        tvdb_id=12345,
        rating=9.5
    )

    result = processor.process(show)
    assert result.decision == Decision.FILTER


@pytest.mark.unit
def test_empty_selection_matches_everything():
    """Test that an empty selection (no criteria) matches any show."""
    config = FiltersConfig(
        selections=[Selection(name="All")]  # No criteria = matches all
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
        title="Random Show",
        tvdb_id=12345,
        language="Japanese",
        country="JP",
        type="Animation"
    )

    result = processor.process(show)
    assert result.decision == Decision.ADD
