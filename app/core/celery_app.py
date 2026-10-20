"""Instance et configuration Celery pour Rockib AI (Beat & Workers)."""
from __future__ import annotations

import logging
from celery import Celery
from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "rockib_ia",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.goal_engine.tasks", "app.execution.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Celery Beat schedule: pulse régulier pour réveiller les Goals et réconcilier les actions
    beat_schedule={
        "dispatch-active-goals-every-5s": {
            "task": "app.goal_engine.tasks.dispatch_active_goals",
            "schedule": 5.0,
        },
        "reconcile-pending-attempts-every-30s": {
            "task": "app.execution.tasks.reconcile_pending_attempts",
            "schedule": 30.0,
        },
    },
)
