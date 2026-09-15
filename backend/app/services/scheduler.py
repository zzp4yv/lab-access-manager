from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.database import SessionLocal
from app.services.lifecycle import run_lifecycle_cycle

logger = logging.getLogger("services.scheduler")
settings = get_settings()

_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    db = SessionLocal()
    try:
        run_lifecycle_cycle(db)
    except Exception:  # noqa: BLE001
        logger.exception("Erro ao executar ciclo de vida agendado")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _job,
        "interval",
        minutes=settings.LIFECYCLE_CHECK_INTERVAL_MINUTES,
        id="lifecycle_cycle",
        next_run_time=None,  # primeira execução agendada normalmente pelo intervalo
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Scheduler de ciclo de vida iniciado (intervalo=%s min)",
        settings.LIFECYCLE_CHECK_INTERVAL_MINUTES,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
