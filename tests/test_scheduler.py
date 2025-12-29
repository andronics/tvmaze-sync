"""Tests for sync scheduler."""

import time
import threading
from datetime import UTC, timedelta, datetime
from unittest.mock import Mock

import pytest

from src.scheduler import Scheduler


def test_scheduler_initialization(mock_sync_func):
    """Test Scheduler initialization."""
    interval = timedelta(hours=6)
    scheduler = Scheduler(interval=interval, sync_func=mock_sync_func)

    assert scheduler.interval == interval
    assert scheduler.sync_func == mock_sync_func
    assert scheduler._stop_event is not None
    assert scheduler._thread is None
    assert scheduler._next_run is None


def test_scheduler_start(short_interval_scheduler):
    """Test scheduler start."""
    scheduler = short_interval_scheduler

    scheduler.start()

    assert scheduler._thread is not None
    assert scheduler._thread.is_alive()
    assert scheduler.is_running is True

    # Cleanup
    scheduler.stop(timeout=2)


def test_scheduler_start_already_running(short_interval_scheduler):
    """Test starting scheduler when already running."""
    scheduler = short_interval_scheduler

    scheduler.start()
    assert scheduler.is_running is True

    # Try to start again - should not create new thread
    original_thread = scheduler._thread
    scheduler.start()

    assert scheduler._thread is original_thread

    # Cleanup
    scheduler.stop(timeout=2)


def test_scheduler_stop_graceful(mock_sync_func):
    """Test graceful scheduler stop."""
    scheduler = Scheduler(interval=timedelta(seconds=10), sync_func=mock_sync_func)

    scheduler.start()
    assert scheduler.is_running is True

    scheduler.stop(timeout=5)

    assert scheduler.is_running is False
    assert scheduler._thread is None or not scheduler._thread.is_alive()


def test_scheduler_stop_timeout(mock_sync_func):
    """Test scheduler stop with timeout."""
    # Create a sync function that takes a long time
    def slow_sync():
        time.sleep(5)

    scheduler = Scheduler(interval=timedelta(seconds=0.1), sync_func=slow_sync)

    scheduler.start()
    time.sleep(0.2)  # Let it start syncing

    # Try to stop with short timeout
    start = time.time()
    scheduler.stop(timeout=1)
    elapsed = time.time() - start

    # Should timeout after approximately 1 second
    assert 0.8 < elapsed < 2


def test_scheduler_trigger_now(mock_sync_func):
    """Test manual trigger."""
    scheduler = Scheduler(interval=timedelta(hours=1), sync_func=mock_sync_func)

    scheduler.start()
    time.sleep(0.1)  # Let scheduler initialize

    # Trigger manually
    scheduler.trigger_now()
    time.sleep(0.2)  # Let it execute

    # Should have been called at least once
    assert mock_sync_func.call_count >= 1

    # Cleanup
    scheduler.stop(timeout=2)


def test_scheduler_next_run_property(mock_sync_func):
    """Test next_run property."""
    scheduler = Scheduler(interval=timedelta(hours=6), sync_func=mock_sync_func)

    scheduler.start()
    time.sleep(0.1)

    next_run = scheduler.next_run

    assert isinstance(next_run, datetime)
    assert next_run > datetime.now(UTC)

    # Cleanup
    scheduler.stop(timeout=2)


def test_scheduler_is_running_property(mock_sync_func):
    """Test is_running property."""
    scheduler = Scheduler(interval=timedelta(hours=1), sync_func=mock_sync_func)

    assert scheduler.is_running is False

    scheduler.start()
    assert scheduler.is_running is True

    scheduler.stop(timeout=2)
    assert scheduler.is_running is False


def test_scheduler_run_loop_normal_execution(mock_sync_func):
    """Test scheduler normal execution loop."""
    scheduler = Scheduler(interval=timedelta(seconds=0.2), sync_func=mock_sync_func)

    scheduler.start()
    time.sleep(0.7)  # Let it run ~3 cycles

    # Should have called sync function multiple times
    assert mock_sync_func.call_count >= 2

    # Cleanup
    scheduler.stop(timeout=2)


def test_scheduler_run_loop_exception_handling():
    """Test scheduler handles exceptions in sync function."""
    call_count = 0

    def failing_sync():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Test error")

    scheduler = Scheduler(interval=timedelta(seconds=0.1), sync_func=failing_sync)

    scheduler.start()
    time.sleep(0.5)  # Let it run and recover from errors

    # Should still be running despite errors
    assert scheduler.is_running is True
    assert call_count >= 3  # Should have retried

    # Cleanup
    scheduler.stop(timeout=2)


def test_scheduler_interval_timing(mock_sync_func):
    """Test that scheduler respects interval timing."""
    interval = timedelta(seconds=0.3)
    scheduler = Scheduler(interval=interval, sync_func=mock_sync_func)

    scheduler.start()
    start = time.time()

    # Wait for 2 cycles
    time.sleep(0.8)

    elapsed = time.time() - start
    calls = mock_sync_func.call_count

    # Should have completed approximately 2-3 calls in ~0.8 seconds
    assert 2 <= calls <= 4

    # Cleanup
    scheduler.stop(timeout=2)


def test_scheduler_thread_safety(mock_sync_func):
    """Test scheduler thread safety with concurrent triggers."""
    scheduler = Scheduler(interval=timedelta(seconds=1), sync_func=mock_sync_func)

    scheduler.start()

    # Trigger from multiple threads
    def trigger():
        scheduler.trigger_now()

    threads = [threading.Thread(target=trigger) for _ in range(5)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    time.sleep(0.5)

    # Should not crash and should handle concurrent triggers
    assert scheduler.is_running is True

    # Cleanup
    scheduler.stop(timeout=2)
