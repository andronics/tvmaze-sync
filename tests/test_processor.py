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
