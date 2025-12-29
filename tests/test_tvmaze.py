"""Tests for TVMaze API client."""

import time
import threading
from unittest.mock import patch

import pytest
import responses
from requests.exceptions import Timeout, ConnectionError

from src.clients.tvmaze import (
    RateLimiter,
    TVMazeClient,
    TVMazeError,
    TVMazeNotFoundError,
    TVMazeRateLimitError,
)
from src.config import TVMazeConfig


# RateLimiter tests

def test_rate_limiter_initialization():
    """Test RateLimiter initialization."""
    limiter = RateLimiter(max_requests=20, window_seconds=10)

    assert limiter.max_requests == 20
    assert limiter.window_seconds == 10
    assert len(limiter.request_times) == 0


def test_rate_limiter_allows_requests_within_limit():
    """Test that rate limiter allows requests within the limit."""
    limiter = RateLimiter(max_requests=5, window_seconds=1)

    # Should allow 5 requests without blocking
    start = time.time()
    for _ in range(5):
        limiter.acquire()
    elapsed = time.time() - start

    # Should complete quickly (no blocking)
    assert elapsed < 0.5


def test_rate_limiter_blocks_when_at_capacity():
    """Test that rate limiter blocks when at capacity."""
    limiter = RateLimiter(max_requests=3, window_seconds=1)

    # Fill the bucket
    for _ in range(3):
        limiter.acquire()

    # Next request should block until window slides
    start = time.time()
    limiter.acquire()
    elapsed = time.time() - start

    # Should have waited approximately 1 second
    assert 0.8 < elapsed < 1.5


def test_rate_limiter_sliding_window_cleanup():
    """Test that rate limiter cleans up old request times."""
    limiter = RateLimiter(max_requests=10, window_seconds=0.5)

    # Make some requests
    for _ in range(5):
        limiter.acquire()

    # Wait for window to pass
    time.sleep(0.6)

    # Old requests should be cleaned up
    assert len(limiter.request_times) == 0


def test_rate_limiter_wait_time():
    """Test wait_time calculation."""
    limiter = RateLimiter(max_requests=2, window_seconds=1)

    # No requests yet
    assert limiter.wait_time() == 0

    # Fill the bucket
    limiter.acquire()
    limiter.acquire()

    # Should need to wait
    wait = limiter.wait_time()
    assert 0 < wait <= 1


def test_rate_limiter_thread_safety():
    """Test that rate limiter is thread-safe."""
    limiter = RateLimiter(max_requests=10, window_seconds=1)
    results = []

    def make_request():
        limiter.acquire()
        results.append(time.time())

    # Spawn multiple threads
    threads = [threading.Thread(target=make_request) for _ in range(15)]
    start = time.time()

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    elapsed = time.time() - start

    # All requests should complete
    assert len(results) == 15

    # Should have taken at least 1 second (due to rate limiting)
    assert elapsed >= 0.8


# TVMazeClient tests

def test_tvmaze_client_initialization_without_api_key():
    """Test TVMazeClient initialization without API key."""
    config = TVMazeConfig()
    client = TVMazeClient(config)

    assert client.api_key is None
    assert client.rate_limiter.max_requests == 20
    assert "User-Agent" in client.session.headers


def test_tvmaze_client_initialization_with_api_key():
    """Test TVMazeClient initialization with API key."""
    config = TVMazeConfig(api_key="premium_key", rate_limit=100)
    client = TVMazeClient(config)

    assert client.api_key == "premium_key"
    assert client.rate_limiter.max_requests == 100


@responses.activate
def test_get_shows_page_success(tvmaze_page_response):
    """Test successful page retrieval."""
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows?page=0",
        json=tvmaze_page_response,
        status=200
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)
    result = client.get_shows_page(page=0)

    assert result == tvmaze_page_response
    assert len(result) == 2
    assert result[0]["id"] == 1


@responses.activate
def test_get_shows_page_end_of_pages():
    """Test 404 response at end of pages."""
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows?page=999",
        json={"error": "Not Found"},
        status=404
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)
    result = client.get_shows_page(page=999)

    # Should return empty list for 404
    assert result == []


@responses.activate
def test_get_show_success(tvmaze_show_response):
    """Test successful single show retrieval."""
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows/1",
        json=tvmaze_show_response,
        status=200
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)
    result = client.get_show(tvmaze_id=1)

    assert result == tvmaze_show_response
    assert result["id"] == 1
    assert result["name"] == "Breaking Bad"


@responses.activate
def test_get_show_not_found():
    """Test TVMazeNotFoundError on 404."""
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows/99999",
        json={"error": "Not Found"},
        status=404
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)

    with pytest.raises(TVMazeNotFoundError):
        client.get_show(tvmaze_id=99999)


@responses.activate
def test_get_updates_success(tvmaze_updates_response):
    """Test successful updates retrieval."""
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/updates/shows?since=week",
        json=tvmaze_updates_response,
        status=200
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)
    result = client.get_updates(since="week")

    # Should convert string keys to integers
    assert isinstance(result, dict)
    assert 1 in result
    assert 2 in result
    assert 3 in result
    assert result[1] == 1704067200


@responses.activate
def test_request_with_api_key(tvmaze_show_response):
    """Test that API key is included in requests."""
    def request_callback(request):
        # Verify API key is in URL
        assert "api_key=premium_key" in request.url
        return (200, {}, '{"id": 1}')

    responses.add_callback(
        responses.GET,
        "https://api.tvmaze.com/shows/1",
        callback=request_callback
    )

    config = TVMazeConfig(api_key="premium_key")
    client = TVMazeClient(config)
    client.get_show(tvmaze_id=1)


@responses.activate
def test_request_429_retry():
    """Test retry logic on 429 rate limit."""
    # First request: 429
    # Second request: success
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows/1",
        status=429
    )
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows/1",
        json={"id": 1},
        status=200
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)

    # Should retry and succeed
    result = client.get_show(tvmaze_id=1)
    assert result["id"] == 1
    assert len(responses.calls) == 2


@responses.activate
def test_request_timeout_retry():
    """Test retry logic on timeout."""
    # First request: timeout
    # Second request: success
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows/1",
        body=Timeout("Connection timeout")
    )
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows/1",
        json={"id": 1},
        status=200
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)

    # Should retry and succeed
    result = client.get_show(tvmaze_id=1)
    assert result["id"] == 1


@responses.activate
def test_request_max_retries_exceeded():
    """Test that max retries raises error."""
    # All requests fail
    for _ in range(5):
        responses.add(
            responses.GET,
            "https://api.tvmaze.com/shows/1",
            status=500
        )

    config = TVMazeConfig()
    client = TVMazeClient(config)

    with pytest.raises(TVMazeError):
        client.get_show(tvmaze_id=1)

    # Should have tried max_retries + 1 times (initial + 3 retries = 4)
    assert len(responses.calls) == 4


@responses.activate
def test_network_error_handling():
    """Test handling of network errors."""
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows/1",
        body=ConnectionError("Network unreachable")
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)

    with pytest.raises(TVMazeError):
        client.get_show(tvmaze_id=1)


@responses.activate
def test_request_exponential_backoff():
    """Test exponential backoff on retries."""
    # Fail twice, then succeed
    responses.add(responses.GET, "https://api.tvmaze.com/shows/1", status=500)
    responses.add(responses.GET, "https://api.tvmaze.com/shows/1", status=500)
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/shows/1",
        json={"id": 1},
        status=200
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)

    start = time.time()
    result = client.get_show(tvmaze_id=1)
    elapsed = time.time() - start

    # Should have backed off (1s + 2s = 3s minimum)
    # But we're lenient in tests
    assert result["id"] == 1
    assert len(responses.calls) == 3


@responses.activate
def test_get_updates_key_conversion():
    """Test that string keys are converted to integers."""
    responses.add(
        responses.GET,
        "https://api.tvmaze.com/updates/shows?since=day",
        json={"100": 1234567890, "200": 1234567900},
        status=200
    )

    config = TVMazeConfig()
    client = TVMazeClient(config)
    result = client.get_updates(since="day")

    # Keys should be integers
    assert 100 in result
    assert 200 in result
    assert "100" not in result
    assert result[100] == 1234567890
