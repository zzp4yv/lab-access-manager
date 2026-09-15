from __future__ import annotations

from app.services.scheduler import start_scheduler, stop_scheduler


def test_scheduler_starts_and_stops_cleanly():
    scheduler = start_scheduler()
    try:
        assert scheduler.running is True
        jobs = scheduler.get_jobs()
        assert any(j.id == "lifecycle_cycle" for j in jobs)
    finally:
        stop_scheduler()
        assert scheduler.running is False


def test_start_scheduler_is_idempotent():
    first = start_scheduler()
    second = start_scheduler()
    try:
        assert first is second
    finally:
        stop_scheduler()
