"""Sync cycle scheduling."""

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Manages sync cycle scheduling.

    Features:
    - Configurable interval
    - Manual trigger support
    - Graceful shutdown
    - Thread-safe
    """

    def __init__(
        self,
        interval: timedelta,
        sync_func: Callable[[], None]
    ):
        self.interval = interval
        self.sync_func = sync_func
        self._stop_event = threading.Event()
        self._trigger_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_run: Optional[datetime] = None
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start scheduler in background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Scheduler already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=False)
        self._thread.start()

        logger.info(f"Scheduler started with interval {self.interval}")

    def stop(self, timeout: float = 300) -> None:
        """
        Stop scheduler gracefully.

        Waits for current cycle to complete up to timeout seconds.
        """
        logger.info("Stopping scheduler...")
        self._stop_event.set()
        self._trigger_event.set()  # Wake up if waiting

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

            if self._thread.is_alive():
                logger.warning(f"Scheduler did not stop within {timeout}s timeout")
            else:
                logger.info("Scheduler stopped successfully")

    def trigger_now(self) -> None:
        """Trigger immediate sync cycle."""
        logger.info("Manual sync trigger requested")
        self._trigger_event.set()

    @property
    def next_run(self) -> Optional[datetime]:
        """Get next scheduled run time."""
        with self._lock:
            return self._next_run

    @property
    def is_running(self) -> bool:
        """Check if sync is currently running."""
        with self._lock:
            return self._running

    def _run_loop(self) -> None:
        """Main scheduler loop."""
        logger.info("Scheduler loop started")

        while not self._stop_event.is_set():
            # Calculate next run time
            with self._lock:
                self._next_run = datetime.utcnow() + self.interval

            # Wait for interval or trigger
            triggered = self._trigger_event.wait(
                timeout=self.interval.total_seconds()
            )
            self._trigger_event.clear()

            if self._stop_event.is_set():
                break

            if triggered:
                logger.info("Running sync cycle (manually triggered)")
            else:
                logger.info("Running sync cycle (scheduled)")

            # Run sync
            with self._lock:
                self._running = True

            try:
                self.sync_func()
            except Exception as e:
                logger.exception("Sync cycle failed")
            finally:
                with self._lock:
                    self._running = False

        logger.info("Scheduler loop exited")
