"""TVMaze API client with rate limiting."""

import logging
import threading
import time
from collections import deque
from typing import Optional

import requests

from ..config import TVMazeConfig

logger = logging.getLogger(__name__)


class TVMazeError(Exception):
    """Base TVMaze API error."""

    pass


class TVMazeNotFoundError(TVMazeError):
    """Show not found (404)."""

    pass


class TVMazeRateLimitError(TVMazeError):
    """Rate limit exceeded (429)."""

    pass


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """
        Block until request is allowed.

        Implements sliding window rate limiting.
        """
        with self._lock:
            now = time.time()

            # Remove timestamps outside the window
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            # If at capacity, wait until oldest request expires
            if len(self._timestamps) >= self.max_requests:
                sleep_time = self._timestamps[0] + self.window_seconds - now
                if sleep_time > 0:
                    logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                    time.sleep(sleep_time)

                    # Clean up again after sleeping
                    now = time.time()
                    cutoff = now - self.window_seconds
                    while self._timestamps and self._timestamps[0] < cutoff:
                        self._timestamps.popleft()

            # Add current timestamp
            self._timestamps.append(now)

    def cleanup(self) -> None:
        """Remove expired timestamps from the sliding window."""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

    def wait_time(self) -> float:
        """Get seconds until next request is allowed."""
        with self._lock:
            now = time.time()

            # Remove timestamps outside the window
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            # If at capacity, calculate wait time
            if len(self._timestamps) >= self.max_requests:
                return max(0, self._timestamps[0] + self.window_seconds - now)

            return 0


class TVMazeClient:
    """
    TVMaze API client.

    Handles:
    - Rate limiting (20 requests / 10 seconds)
    - Automatic retry on 429
    - Response parsing
    """

    BASE_URL = "https://api.tvmaze.com"

    def __init__(self, config: TVMazeConfig):
        self.config = config
        self.session = requests.Session()
        self._rate_limiter = RateLimiter(
            max_requests=config.rate_limit,
            window_seconds=10
        )

        # Add API key if configured
        if config.api_key:
            self.session.params = {'apikey': config.api_key}

        logger.info(f"TVMaze client initialized (rate limit: {config.rate_limit} req/10s)")

    @property
    def rate_limiter(self) -> RateLimiter:
        """Get rate limiter instance."""
        return self._rate_limiter

    def get_shows_page(self, page: int) -> list[dict]:
        """
        Get paginated show index.

        GET /shows?page={page}

        Returns list of show dicts, empty list if 404 (end of pages).
        """
        try:
            response = self._request("GET", f"/shows?page={page}")
            if response.status_code == 404:
                # End of pages
                return []

            response.raise_for_status()
            return response.json()

        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return []
            raise TVMazeError(f"Failed to get shows page {page}: {e}")
        except requests.RequestException as e:
            raise TVMazeError(f"Network error getting shows page {page}: {e}")

    def get_show(self, tvmaze_id: int) -> dict:
        """
        Get single show details.

        GET /shows/{id}

        Raises TVMazeNotFoundError if 404.
        """
        try:
            response = self._request("GET", f"/shows/{tvmaze_id}")

            if response.status_code == 404:
                raise TVMazeNotFoundError(f"Show {tvmaze_id} not found")

            response.raise_for_status()
            return response.json()

        except requests.HTTPError as e:
            if e.response.status_code == 404:
                raise TVMazeNotFoundError(f"Show {tvmaze_id} not found")
            raise TVMazeError(f"Failed to get show {tvmaze_id}: {e}")
        except requests.RequestException as e:
            raise TVMazeError(f"Network error getting show {tvmaze_id}: {e}")

    def get_updates(self, since: str = "week") -> dict[int, int]:
        """
        Get updated show IDs.

        GET /updates/shows?since={since}

        Returns: {tvmaze_id: unix_timestamp, ...}
        """
        try:
            response = self._request("GET", f"/updates/shows?since={since}")
            response.raise_for_status()

            # Response is {tvmaze_id: unix_timestamp}
            data = response.json()

            # Convert string keys to integers
            return {int(k): int(v) for k, v in data.items()}

        except requests.HTTPError as e:
            raise TVMazeError(f"Failed to get updates: {e}")
        except requests.RequestException as e:
            raise TVMazeError(f"Network error getting updates: {e}")

    def _request(
        self,
        method: str,
        endpoint: str,
        max_retries: int = 3,
        **kwargs
    ) -> requests.Response:
        """
        Make rate-limited request.

        Handles:
        - Rate limiting with backoff
        - Retry on 429 and 5xx errors
        - Metric tracking
        """
        url = f"{self.BASE_URL}{endpoint}"

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            # Acquire rate limit token
            self._rate_limiter.acquire()

            try:
                response = self.session.request(method, url, timeout=30, **kwargs)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 10))
                    logger.warning(f"Rate limited by TVMaze, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue

                # Handle server errors with retry
                if 500 <= response.status_code < 600:
                    if attempt < max_retries:
                        backoff = 2 ** attempt
                        logger.warning(f"Server error {response.status_code} for {endpoint}, retrying in {backoff}s (attempt {attempt + 1}/{max_retries + 1})")
                        time.sleep(backoff)
                        continue
                    # Last attempt, let it return so caller can handle

                return response

            except requests.Timeout:
                logger.warning(f"Request timeout for {endpoint} (attempt {attempt + 1}/{max_retries + 1})")
                if attempt >= max_retries:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.RequestException as e:
                logger.error(f"Request failed for {endpoint}: {e}")
                raise

        raise TVMazeRateLimitError(f"Max retries exceeded for {endpoint}")
